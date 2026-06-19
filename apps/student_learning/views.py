import json
import logging
import math
from collections import defaultdict, OrderedDict
from datetime import timedelta
from urllib.parse import urlencode

import datetime

from django.db.models import Count, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.core.student_auth import (
    authenticate_student, login_student, logout_student, student_required,
)
from apps.lessons.models import Lesson, LessonDeployment, LessonStatus
from apps.lessons.services import (
    evaluate_answer, calculate_lesson_mastery, sm2_update,
)
from apps.student_learning.services import award_xp, student_stats, BADGES_CATALOG, level_info, xp_for_next_level
from apps.student_learning.models import LessonProgress, QuizAttempt, Flashcard, StoryAttempt

logger = logging.getLogger(__name__)


# ─── Login / Logout ──────────────────────────────────────────────────────────

def learn_login(request):
    """Login élève via access_code + nom de famille. Public — pas de student_required."""
    if request.session.get('student_id'):
        return redirect('learn:dashboard')

    if request.method == 'GET':
        return render(request, 'learn/login.html', {
            'error': None, 'next': request.GET.get('next', ''),
        })

    access_code = request.POST.get('access_code', '').strip()
    last_name = request.POST.get('last_name', '').strip()

    if not access_code or not last_name:
        return render(request, 'learn/login.html', {
            'error': "Remplis ton code d'accès et ton nom.",
            'next': request.POST.get('next', ''),
        }, status=422)

    student = authenticate_student(access_code, last_name)
    if not student:
        return render(request, 'learn/login.html', {
            'error': "Code d'accès ou nom incorrect. Demande à ton enseignant.",
            'next': request.POST.get('next', ''),
        }, status=422)

    login_student(request, student)

    next_url = request.POST.get('next', '').strip()
    if next_url and next_url.startswith('/learn/'):
        return redirect(next_url)
    return redirect('learn:dashboard')


@require_http_methods(['POST'])
def learn_logout(request):
    logout_student(request)
    return redirect('learn:login')


# ─── Dashboard helpers — concept nodes ───────────────────────────────────────

_SUBJECT_ICONS = {
    'math': '🔢', 'scientific': '🔬', 'literary': '📖',
    'language': '💬', 'geography': '🗺️', 'accounting': '💰', 'code': '💻',
}
_CONCEPT_ICON_HINTS = [
    ('phrase', '📝'), ('verbe', '✏️'), ('conjugaison', '✏️'),
    ('grammaire', '📚'), ('vocabulaire', '💬'), ('lecture', '📖'),
    ('fraction', '½'), ('equation', '⚖️'), ('geometrie', '📐'),
    ('calcul', '🧮'), ('nombre', '🔢'), ('histoire', '📜'),
    ('geo', '🗺️'), ('carte', '🗺️'), ('mot', '💬'),
]
_RING_COLORS = {
    'new': '#818cf8', 'done-weak': '#86efac',
    'done-mid': '#4ade80', 'done-strong': '#fbbf24',
}
_SUBJECT_LUCIDE = {
    'math': 'calculator', 'scientific': 'activity', 'literary': 'pen-line',
    'language': 'globe', 'geography': 'map-pin', 'code': 'code', 'accounting': 'bar-chart-2',
}
_CIRC = round(2 * math.pi * 38, 2)   # SVG r=38 → 238.76


def _humanize_concept_id(cid: str) -> str:
    return cid.replace('_', ' ').capitalize()


def _concept_icon(cid: str, subject_type: str) -> str:
    lower = cid.lower()
    for hint, icon in _CONCEPT_ICON_HINTS:
        if hint in lower:
            return icon
    return _SUBJECT_ICONS.get(subject_type, '📚')


def _concept_state(done: int, total: int) -> str:
    if done == 0:
        return 'new'
    ratio = done / total if total else 0
    if ratio >= 0.8:
        return 'done-strong'
    if ratio >= 0.5:
        return 'done-mid'
    return 'done-weak'


def _stars(done: int, total: int) -> str:
    if not total or done == 0:
        return ''
    ratio = done / total
    if ratio >= 0.8:
        return '★★★'
    if ratio >= 0.5:
        return '★★☆'
    return '★☆☆'


def _build_lesson_concepts(lesson, correct_quiz_set: set) -> list:
    """Construit les groupes de concepts pour le chemin d'apprentissage.
    Priorité : quiz_data.concepts (format riche) → fallback groupement par concept_id."""
    qd = lesson.quiz_data or {}
    quizzes = qd.get('quizzes', [])
    concepts_raw = qd.get('concepts')

    def _enrich(cid, name, icon, order, quiz_ids):
        done = sum(1 for qid in quiz_ids if (lesson.id, qid) in correct_quiz_set)
        total = len(quiz_ids)
        arc_done = round(done / total * _CIRC, 1) if total else 0.0
        state = _concept_state(done, total)
        return {
            'id': cid, 'name': name, 'icon': icon, 'order': order,
            'quiz_ids': quiz_ids, 'done_count': done, 'total_count': total,
            'arc_done': arc_done, 'arc_gap': round(_CIRC - arc_done, 1),
            'state': state, 'stars': _stars(done, total),
            'ring_color': _RING_COLORS.get(state, '#d1d5db'),
            'lucide_icon': _SUBJECT_LUCIDE.get(lesson.subject_type, 'book-open'),
        }

    if concepts_raw:
        return [
            _enrich(c['id'],
                    c.get('name', _humanize_concept_id(c['id'])),
                    c.get('icon', '📚'),
                    c.get('order', i),
                    c.get('quiz_ids', []))
            for i, c in enumerate(concepts_raw[:6], 1)
        ]

    # Fallback : groupement par concept_id, ordre d'apparition dans les quizzes
    seen = list(OrderedDict.fromkeys(
        q.get('concept_id', '') for q in quizzes if q.get('concept_id')
    ))
    by_concept: dict = defaultdict(list)
    for q in quizzes:
        cid = q.get('concept_id', '')
        if cid:
            by_concept[cid].append(q['id'])

    return [
        _enrich(cid,
                _humanize_concept_id(cid),
                _concept_icon(cid, lesson.subject_type),
                order,
                by_concept[cid])
        for order, cid in enumerate(seen[:6], 1)
    ]


# ─── Dashboard ───────────────────────────────────────────────────────────────

@student_required
def learn_dashboard(request):
    student = request.student
    today = timezone.now().date()

    # 1. Matières disponibles dans la classe
    subjects_raw = (
        LessonDeployment.objects
        .filter(school_class=student.school_class, is_active=True,
                lesson__status=LessonStatus.READY)
        .values_list('lesson__subject', 'lesson__subject_type')
        .distinct()
        .order_by('lesson__subject')
    )
    subjects = [{'name': s, 'type': t} for s, t in subjects_raw]

    # 2. Matière active (GET param ou première)
    active_subject = request.GET.get('subject')
    if not active_subject and subjects:
        active_subject = subjects[0]['name']

    # 3. Leçons de la matière active + progression (zéro N+1)
    lessons_data = []
    if active_subject:
        deployments = (
            LessonDeployment.objects
            .filter(school_class=student.school_class, is_active=True,
                    lesson__status=LessonStatus.READY,
                    lesson__subject=active_subject)
            .select_related('lesson')
            .order_by('lesson__created_at')
        )
        lesson_ids = [d.lesson_id for d in deployments]
        progress_map = {
            p.lesson_id: p
            for p in LessonProgress.objects.filter(
                student=student, lesson_id__in=lesson_ids)
        }
        # Batch unique : toutes les bonnes réponses de l'élève sur ces leçons
        correct_quiz_set = set(
            QuizAttempt.objects
            .filter(student=student, lesson_id__in=lesson_ids, is_correct=True)
            .values_list('lesson_id', 'quiz_id')
            .distinct()
        )

        for dep in deployments:
            prog = progress_map.get(dep.lesson_id)
            mastery = calculate_lesson_mastery(student, dep.lesson)
            if (prog and prog.is_completed) or mastery >= 80:
                node_state, progress_pct = 'completed', 100
            elif prog or mastery >= 40:
                node_state = 'in_progress'
                if prog and not prog.is_completed:
                    blocks_total = len(
                        (dep.lesson.structured_content or {}).get('blocks', [])) or 1
                    progress_pct = min(
                        int(prog.last_block_index / blocks_total * 100), 99)
                else:
                    progress_pct = mastery
            else:
                node_state, progress_pct = 'not_started', 0

            lessons_data.append({
                'lesson':       dep.lesson,
                'node_state':   node_state,
                'progress_pct': progress_pct,
                'mastery':      mastery,
                'mastery_arc':  round(mastery / 100 * _CIRC, 1),
                'concepts':     _build_lesson_concepts(dep.lesson, correct_quiz_set),
                'has_story':    bool(dep.lesson.story_data),
            })

    # 4. Leçon en cours
    current_lesson_progress = (
        LessonProgress.objects
        .filter(student=student, is_completed=False)
        .select_related('lesson')
        .order_by('-started_at')
        .first()
    )

    # 5. Streak quotidien
    _update_streak(student, today)

    # 6. Infos niveau
    level_emoji, level_name = level_info(student.current_level)

    return render(request, 'learn/dashboard.html', {
        'student':                 student,
        'subjects':                subjects,
        'active_subject':          active_subject,
        'lessons_data':            lessons_data,
        'current_lesson_progress': current_lesson_progress,
        'today':                   today,
        'learn_toast':             request.session.pop('learn_toast', None),
        'level_emoji':             level_emoji,
        'level_name':              level_name,
        'xp_to_next':              xp_for_next_level(student.total_xp),
        'xp_in_level':             student.total_xp % 500,
    })


def _update_streak(student, today):
    """Met à jour le streak quotidien. Appelé à chaque visite du dashboard."""
    last = student.last_activity_date
    if last == today:
        return
    if last and last == today - timedelta(days=1):
        student.streak_days += 1
    else:
        student.streak_days = 1
    if student.streak_days > student.longest_streak:
        student.longest_streak = student.streak_days
    student.last_activity_date = today
    student.save(update_fields=['streak_days', 'longest_streak', 'last_activity_date'])

    # Bonus de palier (idempotent : streak_days ne passe qu'une fois par valeur).
    if student.streak_days in (7, 30):
        award_xp(student, 100 if student.streak_days == 7 else 500, f'streak_{student.streak_days}')


# ─── Stubs phases suivantes ──────────────────────────────────────────────────

# ─── Lecture leçon (Phase 5) ─────────────────────────────────────────────────

@student_required
def learn_lesson(request, lesson_id):
    student = request.student

    deployment = get_object_or_404(
        LessonDeployment, lesson_id=lesson_id, school_class=student.school_class,
        is_active=True, lesson__status=LessonStatus.READY,
    )
    lesson = deployment.lesson

    progress, _created = LessonProgress.objects.get_or_create(student=student, lesson=lesson)

    blocks = (lesson.structured_content or {}).get('blocks', []) if lesson.structured_content else []

    # Attache la note perso (reflection) à chaque bloc — indexé par block_id.
    notes_map = {n['block_id']: n['text'] for n in (progress.notes or [])}
    for b in blocks:
        b['note'] = notes_map.get(b.get('id'), '')

    total_blocks = len(blocks)
    if total_blocks:
        initial_pct = min(int((progress.last_block_index + 1) / total_blocks * 100), 100)
    else:
        initial_pct = 0

    return render(request, 'learn/lesson.html', {
        'student': student,
        'lesson': lesson,
        'progress': progress,
        'blocks': blocks,
        'total_blocks': total_blocks,
        'initial_pct': initial_pct,
        'has_story': bool(lesson.story_data),
        'has_quiz': lesson.quiz_count > 0,
        'already_done': StoryAttempt.objects.filter(student=student, lesson=lesson).exists(),
        'learn_toast': request.session.pop('learn_toast', None),
    })


@student_required
@require_http_methods(['POST'])
def lesson_save_progress(request, lesson_id):
    """Sauvegarde le dernier bloc lu (background IntersectionObserver). Retourne 204."""
    student = request.student
    try:
        data = json.loads(request.body)
        block_index = int(data.get('block_index', 0))
        time_delta = int(data.get('time_seconds', 0))
    except (ValueError, json.JSONDecodeError):
        return HttpResponse(status=400)

    LessonProgress.objects.filter(student=student, lesson_id=lesson_id).update(
        last_block_index=block_index,
        reading_time_seconds=F('reading_time_seconds') + max(time_delta, 0),
    )
    return HttpResponse(status=204)


@student_required
@require_http_methods(['POST'])
def lesson_save_note(request, lesson_id):
    """Sauvegarde une note personnelle sur un bloc 'reflection'. Retourne 204."""
    student = request.student
    try:
        data = json.loads(request.body)
        block_id = str(data.get('block_id', ''))
        text = str(data.get('text', '')).strip()
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    if not block_id:
        return HttpResponse(status=400)

    progress = get_object_or_404(LessonProgress, student=student, lesson_id=lesson_id)
    notes = progress.notes or []
    updated = False
    for note in notes:
        if note['block_id'] == block_id:
            note['text'] = text
            note['updated_at'] = timezone.now().isoformat()
            updated = True
            break
    if not updated and text:
        notes.append({'block_id': block_id, 'text': text, 'created_at': timezone.now().isoformat()})

    progress.notes = notes
    progress.save(update_fields=['notes'])
    return HttpResponse(status=204)


@student_required
@require_http_methods(['POST'])
def lesson_complete(request, lesson_id):
    """Marque la leçon complétée + 20 XP (inline, centralisé en Phase 9). Redirige au dashboard."""
    student = request.student

    deployment = get_object_or_404(
        LessonDeployment, lesson_id=lesson_id, school_class=student.school_class, is_active=True,
    )
    lesson = deployment.lesson

    progress, _ = LessonProgress.objects.get_or_create(student=student, lesson=lesson)

    if not progress.is_completed:
        progress.is_completed = True
        progress.completed_at = timezone.now()
        progress.save(update_fields=['is_completed', 'completed_at'])

        # Création des flashcards (Option B — à la complétion, idempotent).
        flashcards_raw = (lesson.flashcards_data or {}).get('flashcards', [])
        if flashcards_raw:
            today = timezone.localdate()
            existing_ids = set(
                Flashcard.objects.filter(student=student, lesson=lesson)
                .values_list('flashcard_id', flat=True)
            )
            new_cards = [
                Flashcard(student=student, lesson=lesson,
                          flashcard_id=fc['id'], next_review_date=today)
                for fc in flashcards_raw if fc.get('id') and fc['id'] not in existing_ids
            ]
            if new_cards:
                Flashcard.objects.bulk_create(new_cards, ignore_conflicts=True)

        # XP centralisé (recalcule niveau + badges, détecte montée de niveau).
        xp_result = award_xp(student, 20, 'lecon_completee')
        level_msg = ''
        if xp_result['leveled_up']:
            level_msg = f" · {xp_result['level_emoji']} Niveau {xp_result['new_level']} {xp_result['level_name']} !"
        request.session['learn_toast'] = f"🎉 Leçon complétée ! +20 XP{level_msg}"

    return redirect(f"{reverse('learn:dashboard')}?{urlencode({'subject': lesson.subject})}")


# ─── Quiz engine (Phase 6) ───────────────────────────────────────────────────

def _student_deployment(student, lesson_id, require_ready=True):
    flt = dict(lesson_id=lesson_id, school_class=student.school_class, is_active=True)
    if require_ready:
        flt['lesson__status'] = LessonStatus.READY
    return get_object_or_404(LessonDeployment, **flt)


@student_required
def learn_quiz(request, lesson_id):
    """Moteur quiz question par question (état client Alpine, réponses jamais envoyées au client)."""
    student = request.student
    lesson = _student_deployment(student, lesson_id).lesson

    quizzes = (lesson.quiz_data or {}).get('quizzes', [])
    if not quizzes:
        return redirect('learn:lesson', lesson_id=lesson_id)

    # Payload client SANS les réponses (anti-triche : answer/answer_index/explanation/hint retirés).
    client_quizzes = [{
        'id': q.get('id'),
        'type': q.get('type', 'mcq'),
        'question': q.get('question', ''),
        'options': q.get('options', []),
        'image_url': q.get('image_url'),
    } for q in quizzes]
    has_ordering = any(q.get('type') == 'ordering' for q in quizzes)

    return render(request, 'learn/quiz.html', {
        'student': student,
        'lesson': lesson,
        'client_quizzes': client_quizzes,   # injecté via |json_script (sûr, sans réponses)
        'total': len(quizzes),
        'has_ordering': has_ordering,
    })


@student_required
@require_http_methods(['POST'])
def quiz_submit(request, lesson_id):
    """Évalue une réponse, crée QuizAttempt, accorde +5 XP à la 1re bonne réponse. JSON."""
    student = request.student
    try:
        data = json.loads(request.body)
        quiz_id = str(data.get('quiz_id', ''))
        student_answer = data.get('answer')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Données invalides'}, status=400)

    lesson = _student_deployment(student, lesson_id, require_ready=False).lesson
    quizzes = (lesson.quiz_data or {}).get('quizzes', [])
    quiz = next((q for q in quizzes if q.get('id') == quiz_id), None)
    if not quiz:
        return JsonResponse({'error': 'Quiz introuvable'}, status=404)

    # 1re bonne réponse ? (vérifié AVANT de créer la tentative → anti-farming fiable)
    already_correct = QuizAttempt.objects.filter(
        student=student, lesson=lesson, quiz_id=quiz_id, is_correct=True,
    ).exists()

    is_correct = evaluate_answer(quiz, student_answer)

    QuizAttempt.objects.create(
        student=student, lesson=lesson, quiz_id=quiz_id,
        question_type=quiz.get('type', 'mcq'),
        student_answer=student_answer if isinstance(student_answer, (dict, list)) else str(student_answer),
        is_correct=is_correct,
        time_spent_seconds=min(int(data.get('time_seconds', 0) or 0), 32000),
    )

    xp_earned = 0
    level_payload = {'leveled_up': False, 'new_level': None, 'level_emoji': '', 'level_name': '', 'new_badges': []}
    if is_correct and not already_correct:
        xp_earned = 5
        r = award_xp(student, 5, 'quiz_correct')   # recalcule niveau + badges (corrige le bug niveau quiz)
        level_payload = {
            'leveled_up': r['leveled_up'], 'new_level': r['new_level'],
            'level_emoji': r['level_emoji'], 'level_name': r['level_name'],
            'new_badges': r['new_badges'],
        }

    return JsonResponse({
        'correct': is_correct,
        'explanation': quiz.get('explanation', ''),
        'correct_answer': quiz.get('answer', ''),
        'correct_index': quiz.get('answer_index', -1),
        'xp_earned': xp_earned,
        'mastery': calculate_lesson_mastery(student, lesson),
        'hint': quiz.get('hint', ''),
        **level_payload,
    })


@student_required
def quiz_results(request, lesson_id):
    """Résultats : score (dernières tentatives), XP, bonus 100% (idempotent)."""
    student = request.student
    lesson = _student_deployment(student, lesson_id, require_ready=False).lesson

    quizzes = (lesson.quiz_data or {}).get('quizzes', [])
    total = len(quizzes)
    if total == 0:
        return redirect('learn:lesson', lesson_id=lesson_id)

    # Score = dernière tentative par quiz_id (1 requête, distinct on).
    quiz_ids = [q['id'] for q in quizzes]
    latest = (
        QuizAttempt.objects
        .filter(student=student, lesson=lesson, quiz_id__in=quiz_ids)
        .order_by('quiz_id', '-attempted_at')
        .distinct('quiz_id')
        .values_list('is_correct', flat=True)
    )
    correct = sum(1 for ok in latest if ok)
    score_pct = int(correct / total * 100)
    mastery = calculate_lesson_mastery(student, lesson)

    # Bonus 100% accordé UNE SEULE FOIS (flag sur LessonProgress → idempotent).
    bonus_xp = 0
    if score_pct == 100:
        progress, _ = LessonProgress.objects.get_or_create(student=student, lesson=lesson)
        if not progress.quiz_bonus_awarded:
            bonus_xp = 30
            progress.quiz_bonus_awarded = True
            progress.save(update_fields=['quiz_bonus_awarded'])
            award_xp(student, 30, 'quiz_parfait')   # recalcule niveau + badge quiz_parfait

    return render(request, 'learn/quiz_results.html', {
        'student': student,
        'lesson': lesson,
        'correct': correct,
        'total': total,
        'errors': total - correct,
        'score_pct': score_pct,
        'mastery': mastery,
        'bonus_xp': bonus_xp,
        'xp_from_quiz': correct * 5 + bonus_xp,
    })


# ─── Flashcards SM-2 (Phase 8) ───────────────────────────────────────────────

@student_required
def learn_flashcards(request):
    """Paquets de flashcards par leçon (dues / total). 3 requêtes, zéro N+1."""
    student = request.student
    today = timezone.localdate()

    lesson_ids = (Flashcard.objects.filter(student=student)
                  .values_list('lesson_id', flat=True).distinct())
    lessons = Lesson.objects.filter(id__in=lesson_ids).only(
        'id', 'title', 'subject', 'subject_type')

    due_counts = {r['lesson_id']: r['cnt'] for r in (
        Flashcard.objects.filter(student=student, next_review_date__lte=today)
        .values('lesson_id').annotate(cnt=Count('id')))}
    total_counts = {r['lesson_id']: r['cnt'] for r in (
        Flashcard.objects.filter(student=student)
        .values('lesson_id').annotate(cnt=Count('id')))}

    paquets = []
    for l in lessons:
        due = due_counts.get(l.id, 0)
        total = total_counts.get(l.id, 0)
        paquets.append({'lesson': l, 'due': due, 'total': total, 'reviewed': total - due})
    paquets.sort(key=lambda x: -x['due'])

    return render(request, 'learn/flashcards.html', {
        'student': student,
        'paquets': paquets,
        'total_due': sum(p['due'] for p in paquets),
    })


@student_required
def flashcards_session(request, lesson_id):
    """Session de révision : flashcards dues d'une leçon."""
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id)

    due_cards = list(
        Flashcard.objects.filter(
            student=student, lesson=lesson,
            next_review_date__lte=timezone.localdate(),
        ).order_by('next_review_date')
    )
    if not due_cards:
        return redirect('learn:flashcards')

    fc_map = {fc['id']: fc for fc in (lesson.flashcards_data or {}).get('flashcards', [])}
    session_cards = [{
        'db_id': c.id,
        'flashcard_id': c.flashcard_id,
        'front': fc_map.get(c.flashcard_id, {}).get('front', ''),
        'back': fc_map.get(c.flashcard_id, {}).get('back', ''),
    } for c in due_cards]

    return render(request, 'learn/flashcards_session.html', {
        'student': student,
        'lesson': lesson,
        'session_cards': session_cards,
        'total': len(session_cards),
    })


@student_required
@require_http_methods(['POST'])
def flashcard_review(request, card_id):
    """Enregistre la qualité, applique SM-2. JSON."""
    student = request.student
    card = get_object_or_404(Flashcard, pk=card_id, student=student)

    try:
        data = json.loads(request.body)
        quality = int(data.get('quality', 1))
        if quality not in (1, 2, 4, 5):
            quality = 1
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Données invalides'}, status=400)

    today = timezone.localdate()
    # Anti-farming : +2 XP seulement si la carte était DUE (1re révision du cycle).
    # Les re-passages d'une carte ratée dans la session ont déjà next_review_date > today.
    was_due = card.next_review_date <= today

    new_reps, new_ef, new_interval = sm2_update(
        card.repetitions, card.ease_factor, card.interval_days, quality)
    next_review = today + datetime.timedelta(days=new_interval)

    card.repetitions = new_reps
    card.ease_factor = new_ef
    card.interval_days = new_interval
    card.next_review_date = next_review
    card.last_quality = quality
    card.total_reviews += 1
    card.save(update_fields=[
        'repetitions', 'ease_factor', 'interval_days',
        'next_review_date', 'last_quality', 'total_reviews',
    ])

    if was_due:
        award_xp(student, 2, 'flashcard_revisee')

    return JsonResponse({
        'next_review_days': new_interval,
        'next_review_date': next_review.isoformat(),
        'quality': quality,
    })


# ─── Profil (Phase 9) ────────────────────────────────────────────────────────

@student_required
def learn_profile(request):
    student = request.student
    return render(request, 'learn/profile.html', {
        'student': student,
        'stats': student_stats(student),
        'badges_catalog': BADGES_CATALOG,
    })


# ─── Stories interactives (Phase 10) ─────────────────────────────────────────

CHAR_COLORS = {
    'aminata': '#FF6B6B', 'moussa': '#4ECDC4', 'fatoumata': '#A855F7',
    'ibrahima': '#F59E0B', 'boubacar': '#10B981', 'mariam': '#EC4899',
    'kadiatou': '#6366F1', 'oumar': '#14B8A6',
}
CHAR_DEFAULT_COLOR = '#6B7280'


def _char_color(name: str) -> str:
    return CHAR_COLORS.get((name or '').lower().strip(), CHAR_DEFAULT_COLOR)


@student_required
def learn_story(request, lesson_id):
    """Story interactive (dialogue type messagerie). expected jamais exposé au client."""
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    get_object_or_404(LessonDeployment, lesson_id=lesson_id,
                      school_class=student.school_class, is_active=True)

    if not lesson.story_data:
        return redirect('learn:lesson', lesson_id=lesson_id)

    story = lesson.story_data

    characters = {}
    for char in story.get('characters', []):
        name = char.get('name', '')
        characters[name] = {
            'name': name, 'role': char.get('role', ''),
            'side': char.get('side', 'left'),
            'color': _char_color(name),
            'initial': name[0].upper() if name else '?',
        }

    # Dialogue SANS expected (anti-triche).
    dialogue_safe = []
    for item in story.get('dialogue', []):
        itype = item.get('type', 'narration')
        entry = {'type': itype, 'text': item.get('text', '')}
        if itype in ('speech', 'question'):
            name = item.get('speaker', '')
            entry['speaker'] = name
            entry['side'] = characters.get(name, {}).get('side', 'left')
            entry['color'] = _char_color(name)
            entry['initial'] = name[0].upper() if name else '?'
            if itype == 'question':
                entry['marker'] = item.get('marker', '')
        dialogue_safe.append(entry)

    questions_safe = {
        q['marker']: {'question': q.get('question', ''), 'concept_ref': q.get('concept_ref', '')}
        for q in story.get('questions', []) if q.get('marker')
    }

    return render(request, 'learn/story.html', {
        'student': student,
        'lesson': lesson,
        'characters': characters,
        'dialogue': dialogue_safe,
        'questions_safe': questions_safe,
        'total_questions': len(questions_safe),
        'already_done': StoryAttempt.objects.filter(student=student, lesson=lesson).exists(),
        'setting': story.get('setting', ''),
        'title': story.get('title', 'Histoire'),
    })


@student_required
@require_http_methods(['POST'])
def story_answer(request, lesson_id):
    """Évalue une réponse de story (expected côté serveur, tolérance inclusion)."""
    from apps.lessons.services import normalize_text
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id)

    try:
        data = json.loads(request.body)
        marker = str(data.get('marker', ''))
        student_answer = str(data.get('answer', '')).strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid'}, status=400)

    question = next(
        (q for q in (lesson.story_data or {}).get('questions', []) if q.get('marker') == marker),
        None,
    )
    if not question:
        return JsonResponse({'error': 'Question non trouvée'}, status=404)

    s = normalize_text(student_answer)
    e = normalize_text(question.get('expected', ''))
    is_correct = bool(e) and (s == e or s in e or e in s)

    feedback = (f"Exactement ! {question['expected']} est la bonne réponse."
                if is_correct else
                f"Pas tout à fait... La réponse était : {question['expected']}")

    return JsonResponse({'correct': is_correct, 'feedback': feedback, 'expected': question.get('expected', '')})


@student_required
@require_http_methods(['POST'])
def story_finish(request, lesson_id):
    """Crée StoryAttempt + XP (1re complétion uniquement, ≥50% → +25, 100% → +40)."""
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id)

    try:
        data = json.loads(request.body)
        score = max(0, min(int(data.get('score', 0)), 100))
        answers = data.get('answers', [])
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid'}, status=400)

    # 1re complétion = aucun StoryAttempt avant celui qu'on va créer.
    first_time = not StoryAttempt.objects.filter(student=student, lesson=lesson).exists()
    StoryAttempt.objects.create(student=student, lesson=lesson, score=score, answers=answers)

    xp_earned = 0
    if first_time and score >= 50:
        xp_earned = 40 if score == 100 else 25
        award_xp(student, xp_earned, 'story_completee')

    return JsonResponse({'xp_earned': xp_earned, 'score': score})


# ─── Notes & Rangs (Phase 11) ────────────────────────────────────────────────

@student_required
def learn_grades(request):
    """Rang, notes par matière (BulletinLine) et bulletins publiés de l'élève."""
    from apps.schools.models import Bulletin, BulletinLine, Note

    student = request.student

    bulletins = list(
        Bulletin.objects
        .filter(student=student, is_published=True, is_cancelled=False)
        .select_related('period', 'period__school_year')
        .order_by('-published_at')
    )
    current_bulletin = bulletins[0] if bulletins else None
    previous_bulletin = bulletins[1] if len(bulletins) > 1 else None

    # Tendance de rang (rang plus petit = meilleur).
    rank_trend = None
    if current_bulletin and previous_bulletin and current_bulletin.rank and previous_bulletin.rank:
        diff = previous_bulletin.rank - current_bulletin.rank
        rank_trend = 'up' if diff > 0 else 'down' if diff < 0 else 'stable'

    # Notes par matière = lignes du bulletin courant (1 par matière, moyenne finale).
    subject_lines = []
    if current_bulletin:
        subject_lines = list(
            current_bulletin.lines
            .filter(final_average__isnull=False)
            .select_related('class_subject__subject')
            .order_by('class_subject__order', 'class_subject__subject__name')
        )

    return render(request, 'learn/grades.html', {
        'student': student,
        'bulletins': bulletins,
        'current_bulletin': current_bulletin,
        'rank_trend': rank_trend,
        'subject_lines': subject_lines,
        'has_pending_notes': Note.objects.filter(student=student, is_cancelled=False).exists(),
    })


@student_required
def learn_bulletin_pdf(request, bulletin_id):
    """PDF d'un bulletin — uniquement celui de l'élève connecté, publié."""
    from apps.schools.models import Bulletin
    from apps.schools.services.bulletin_pdf import generate_bulletin_pdf

    bulletin = get_object_or_404(
        Bulletin, pk=bulletin_id,
        student=request.student, is_published=True, is_cancelled=False,
    )
    try:
        pdf_bytes = generate_bulletin_pdf(bulletin)
    except Exception as e:
        logger.error('PDF bulletin élève %s erreur: %s', bulletin_id, e)
        return HttpResponse('Erreur génération PDF', status=500)

    name = request.student.full_name.replace(' ', '_')
    period = str(bulletin.period).replace(' ', '_').replace('—', '-')
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="bulletin_{name}_{period}.pdf"'
    return resp
