import json
import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.core.student_auth import (
    authenticate_student, login_student, logout_student, student_required,
)
from apps.lessons.models import LessonDeployment, LessonStatus
from apps.lessons.services import evaluate_answer, calculate_lesson_mastery
from apps.student_learning.models import LessonProgress, QuizAttempt

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

        for dep in deployments:
            prog = progress_map.get(dep.lesson_id)
            mastery = calculate_lesson_mastery(student, dep.lesson)
            # Node done si lecture terminée OU mastery quiz >= 80% (décision Phase 6).
            if (prog and prog.is_completed) or mastery >= 80:
                node_state, progress_pct = 'completed', 100
            elif prog or mastery >= 40:
                node_state = 'in_progress'
                if prog and not prog.is_completed:
                    blocks_total = len((dep.lesson.structured_content or {}).get('blocks', [])) or 1
                    progress_pct = min(int(prog.last_block_index / blocks_total * 100), 99)
                else:
                    progress_pct = mastery
            else:
                node_state, progress_pct = 'not_started', 0

            lessons_data.append({
                'lesson': dep.lesson,
                'node_state': node_state,
                'progress_pct': progress_pct,
                'mastery': mastery,
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

    return render(request, 'learn/dashboard.html', {
        'student': student,
        'subjects': subjects,
        'active_subject': active_subject,
        'lessons_data': lessons_data,
        'current_lesson_progress': current_lesson_progress,
        'today': today,
        'learn_toast': request.session.pop('learn_toast', None),
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

        # XP minimal (sera migré vers award_xp() en Phase 9). student est chargé frais → pas de course critique ici.
        student.total_xp += 20
        student.current_level = student.total_xp // 500 + 1
        student.save(update_fields=['total_xp', 'current_level'])

        request.session['learn_toast'] = '🎉 Leçon complétée ! +20 XP'

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
    if is_correct and not already_correct:
        xp_earned = 5
        from apps.students.models import Student
        Student.objects.filter(pk=student.pk).update(total_xp=F('total_xp') + 5)

    return JsonResponse({
        'correct': is_correct,
        'explanation': quiz.get('explanation', ''),
        'correct_answer': quiz.get('answer', ''),
        'correct_index': quiz.get('answer_index', -1),
        'xp_earned': xp_earned,
        'mastery': calculate_lesson_mastery(student, lesson),
        'hint': quiz.get('hint', ''),
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
            from apps.students.models import Student
            Student.objects.filter(pk=student.pk).update(total_xp=F('total_xp') + 30)

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


@student_required
def learn_flashcards_stub(request):
    return render(request, 'learn/stub.html', {'student': request.student, 'title': 'Flashcards', 'phase': 8})


@student_required
def learn_profile_stub(request):
    return render(request, 'learn/stub.html', {'student': request.student, 'title': 'Mon Profil', 'phase': 9})
