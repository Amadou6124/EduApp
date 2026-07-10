import json
import logging
from datetime import timedelta
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.core.student_auth import (
    authenticate_student, login_student, logout_student, student_required,
)
from apps.lessons.models import Lesson, LessonContentVersion, LessonDeployment, LessonStatus
from apps.student_learning.models import (
    QuizAttempt, StoryAttempt,
    ConceptProgress, ExamAttempt, QuestionDraw, StudentNote,
)

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

def _student_v2_lessons(student):
    """Leçons v2 actives READY déployées dans la classe de l'élève, ordonnées
    (matière puis date). Retourne [{id, title, subject, url}] — réutilisé par le
    reroutage de /learn/ et le switcher 'Mes leçons' du parcours v2."""
    deps = (
        LessonDeployment.objects
        .filter(school_class=student.school_class, is_active=True,
                lesson__status=LessonStatus.READY, lesson__format_version=2)
        .select_related('lesson', 'lesson__active_content_version')
        .order_by('lesson__subject', 'lesson__created_at')
    )
    out, seen = [], set()
    for d in deps:
        if d.lesson_id in seen:
            continue
        seen.add(d.lesson_id)
        acv = d.lesson.active_content_version
        out.append({
            'id': d.lesson_id,
            'title': d.lesson.title,
            'subject': d.lesson.subject or '',
            'color': (acv.color if acv and acv.color else '#818CF8'),
            'url': reverse('learn:parcours-v2', kwargs={'lesson_id': d.lesson_id}),
        })
    return out


@student_required
def learn_dashboard(request):
    student = request.student

    # L'accueil élève EST le parcours v2 :
    #   • ≥1 leçon v2  → redirige vers le parcours v2 par défaut (1ère leçon v2)
    #   • 0 leçon v2   → écran vide v2
    # (Le rendu zigzag v1 plus bas est désormais inatteignable — retiré au LOT 4.)
    v2_lessons = _student_v2_lessons(student)
    if v2_lessons:
        return redirect('learn:parcours-v2', lesson_id=v2_lessons[0]['id'])
    return render(request, 'student_learning/empty_v2.html', {'student': student})


@student_required
def learn_profil(request):
    """Profil élève : identité + réglages (thème) + stats d'activité + déconnexion.
    (Gamification XP/streak à venir — award_xp pas encore câblé.)"""
    student = request.student
    cls = student.school_class

    quiz_ok = (QuizAttempt.objects.filter(student=student, is_correct=True)
               .values('quiz_id').distinct().count())
    stories = (StoryAttempt.objects.filter(student=student)
               .values('content_version').distinct().count())
    exams = (ExamAttempt.objects.filter(student=student, passed=True)
             .values('content_version').distinct().count())

    parts = (student.full_name or '').split()
    initials = ''.join(p[0] for p in parts[:2]).upper() or '?'

    return render(request, 'student_learning/profil_v2.html', {
        'active_tab':  'profil',
        'student':     student,
        'initials':    initials,
        'class_name':  cls.name if cls else '',
        'school_name': student.school.name if student.school_id else '',
        'stats':       {'quiz': quiz_ok, 'stories': stories, 'exams': exams},
        'parcours_url': reverse('learn:dashboard'),
        'logout_url':   reverse('learn:logout'),
    })


# ─── PLOMBERIE Notes & Profil — données préservées (affichage clair v1 retiré) ──
# L'ancien affichage clair (learn/base_student.html + grades.html + profile.html)
# a été supprimé. La LOGIQUE DE DONNÉES est conservée ici pour rebrancher les
# futures pages dark v2 :
#   • Profil : student_stats(student) + BADGES_CATALOG (services.py) — déjà autonome.
#   • Notes  : student_grades_context(student) ci-dessous.

def student_grades_context(student) -> dict:
    """PLOMBERIE Notes — à rebrancher sur la future page dark v2.

    Rang, notes par matière (BulletinLine) et bulletins publiés de l'élève.
    Retourne le context dict — SANS render (l'affichage clair a été retiré)."""
    from apps.schools.models import Bulletin, Note

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

    return {
        'student': student,
        'bulletins': bulletins,
        'current_bulletin': current_bulletin,
        'rank_trend': rank_trend,
        'subject_lines': subject_lines,
        'has_pending_notes': Note.objects.filter(student=student, is_cancelled=False).exists(),
    }


def student_progress_context(student):
    """Volet « À l'école » de la page Progrès — assemble 3 couches, chacune
    OPTIONNELLE (rien d'obligatoire pour l'école, aucun blocage) :

      • bulletin publié de la période courante → officiel (moyenne, rang+tendance, PDF)
      • sinon, notes de la période → moyennes PROVISOIRES (même logique que le parent)
      • évaluations formatives PUBLIÉES au parent → fil daté (points d'étape)

    Défensif : pas d'année/période/note → chaque bloc reste None et disparaît.
    Barème lu des vraies données (max_grade par matière), jamais figé à /20.
    """
    from decimal import Decimal
    from collections import OrderedDict
    from apps.schools.models import Bulletin, Note, FormativeGrade
    from apps.schools.periods import (
        active_year_for, periods_for_student, resolve_active_period,
    )

    ctx = {'bulletin': None, 'subject_rows': [], 'is_provisional': False,
           'evals': [], 'period_label': ''}

    year = active_year_for(student.school)
    period = resolve_active_period(periods_for_student(student, year))

    # ── 1. Bulletin publié de la période courante (officiel) ──
    bulletin = None
    if period is not None:
        bulletin = (
            Bulletin.objects
            .filter(student=student, period=period, is_published=True, is_cancelled=False)
            .prefetch_related('lines__class_subject__subject')
            .select_related('period').first()
        )

    if bulletin is not None:
        ctx['period_label'] = str(bulletin.period)
        # Tendance de rang vs bulletin publié précédent (rang plus petit = mieux).
        prev = (Bulletin.objects
                .filter(student=student, is_published=True, is_cancelled=False)
                .exclude(pk=bulletin.pk).select_related('period')
                .order_by('-published_at').first())
        rank_trend, rank_delta = None, None
        if bulletin.rank and prev and prev.rank:
            diff = prev.rank - bulletin.rank
            rank_trend = 'up' if diff > 0 else 'down' if diff < 0 else 'stable'
            rank_delta = abs(diff)

        lines = list(bulletin.lines.filter(final_average__isnull=False)
                     .select_related('class_subject__subject')
                     .order_by('class_subject__order', 'class_subject__subject__name'))
        maxes = [ln.class_subject.max_grade for ln in lines if ln.class_subject.max_grade]
        bul_max = max(maxes) if maxes else Decimal('20')
        ctx['bulletin'] = {
            'average': bulletin.general_average,
            'max': bul_max,
            'rank': bulletin.rank,
            'class_size': bulletin.class_size,
            'first_average': bulletin.first_average,
            'appreciation': bulletin.appreciation,
            'rank_trend': rank_trend,
            'rank_delta': rank_delta,
            'pdf_url': reverse('learn:bulletin-pdf', kwargs={'bulletin_id': bulletin.pk}),
        }
        for ln in lines:
            ctx['subject_rows'].append({
                'subject': ln.class_subject.subject,
                'max': ln.class_subject.max_grade or Decimal('20'),
                'average': ln.final_average,
                'rank': ln.rank_in_subject,
                'appreciation': ln.appreciation,
            })

    # ── 2. Sinon : moyennes PROVISOIRES depuis les notes de la période ──
    elif period is not None:
        notes = list(Note.objects
                     .filter(student=student, period=period, is_cancelled=False)
                     .select_related('class_subject__subject'))
        by_sub = OrderedDict()
        for n in notes:
            cs = n.class_subject
            row = by_sub.setdefault(cs.subject_id, {
                'subject': cs.subject, 'max': cs.max_grade or Decimal('20'),
                'devoir': None, 'compo': None,
            })
            if n.position == 2 or n.note_type == 'composition':
                row['compo'] = n.value
            else:
                row['devoir'] = n.value
        for row in by_sub.values():
            vals = [v for v in (row['devoir'], row['compo']) if v is not None]
            row['average'] = (sum(vals) / len(vals)) if vals else None
        prov_rows = [r for r in by_sub.values() if r['average'] is not None]
        if prov_rows:
            ctx['is_provisional'] = True
            ctx['period_label'] = str(period)
            ctx['subject_rows'] = prov_rows
            # moyenne provisoire globale = moyenne simple des matières notées
            avg = sum(r['average'] for r in prov_rows) / len(prov_rows)
            maxes = [r['max'] for r in prov_rows]
            ctx['provisional_avg'] = avg
            ctx['provisional_max'] = max(maxes) if maxes else Decimal('20')

    # ── 3. Évaluations formatives PUBLIÉES au parent (fil daté, 5 dernières) ──
    grades = (FormativeGrade.objects
              .filter(student=student, value__isnull=False, is_absent=False,
                      evaluation__is_published_to_parent=True)
              .select_related('evaluation', 'evaluation__class_subject__subject')
              .order_by('-evaluation__date', '-evaluation__id')[:5])
    for g in grades:
        ev = g.evaluation
        ctx['evals'].append({
            'title': ev.title or ev.get_eval_type_display(),
            'subject': ev.class_subject.subject.name,
            'date': ev.date,
            'value': g.value,
            'max': ev.max_grade,
        })

    ctx['has_school'] = bool(ctx['bulletin'] or ctx['subject_rows'] or ctx['evals'])
    return ctx


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


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, écran PARCOURS (Phase C).
# Constantes/maths du chemin (px/py, anneau, segments de Bézier) + assemblage des
# nœuds. Partagé par la vue réelle learn_parcours_v2.
# ═══════════════════════════════════════════════════════════════════════════════
import math as _math

_PCRS_TYPE = {
    'story':      {'label': "Histoire", 'cta': "Jouer l'histoire",  'g0': "#FB7185", 'g1': "#F59E0B",
                   'dark': "#BE123C", 'glow': "rgba(251,113,133,.45)", 'icon': "drama"},
    'quiz':       {'label': "Quiz",     'cta': "Commencer le quiz", 'g0': "#22D3EE", 'g1': "#3B82F6",
                   'dark': "#1D4ED8", 'glow': "rgba(34,211,238,.45)", 'icon': "target"},
    'checkpoint': {'label': "Examen",   'cta': "Passer l'examen",   'g0': "#FBBF24", 'g1': "#F59E0B",
                   'dark': "#B45309", 'glow': "rgba(251,191,36,.5)",  'icon': "crown"},
}
_PCRS_COL_W, _PCRS_NODE, _PCRS_ROW_H, _PCRS_AMP, _PCRS_CX = 300, 74, 108, 60, 150


def _pcrs_px(i):
    return round(_PCRS_CX + _PCRS_AMP * _math.sin(i * 0.9), 2)


def _pcrs_py(i):
    return i * _PCRS_ROW_H + 80


def _pcrs_ring_dash(seg, seg_done):
    """Port du calcul d'anneau segmenté (ProgressRing). Retourne (track, fill, cap)."""
    gap = 6
    unit = 100 / seg
    s_len = unit - gap
    track = f"{s_len:.2f} {gap}"
    if seg_done <= 0:                 # aucune passe faite → ne RIEN remplir (pas d'anneau plein)
        return track, "0 100", "butt"
    parts = []
    for i in range(seg_done):
        parts.append(f"{s_len:.2f}")
        if i < seg_done - 1:
            parts.append(str(gap))
    used = seg_done * s_len + max(0, seg_done - 1) * gap
    parts.append(f"{100 - used:.2f}")
    return track, " ".join(parts), "butt"


def assemble_nodes(cv, student):
    """
    Assemble la liste plate des nœuds du parcours (spec §3.4).

    Contrat d'entrée :
        cv      — LessonContentVersion (avec concepts_data list, story_data, exam_data)
        student — instance Student (utilisée pour lire ConceptProgress)

    Contrat de sortie : liste de dicts prêts pour parcours_v2.html (json_script).
    Chaque dict a les clés :
        i, type, title, desc, status, xp, passes, passes_done,
        x, y, show_ring, ring, url_lecteur
        + les clés de _PCRS_TYPE (label, cta, g0, g1, dark, glow, icon)

    Statuts (séquentiels) :
        done    — passes_done >= passes (quiz) ou flag explicite (story/exam)
        current — premier nœud non-done
        locked  — tout ce qui suit le premier nœud non-done
    """
    concepts = cv.concepts_data if isinstance(cv.concepts_data, list) else []
    has_story = bool(cv.story_data)
    has_exam = bool(cv.exam_data)
    url_lecteur = reverse('learn:lecteur-v2', kwargs={'lesson_id': cv.lesson_id})

    # Progression depuis la base (lecture seule — aucune écriture ici)
    cprog = {
        cp.concept_id: cp.passes_done
        for cp in ConceptProgress.objects.filter(student=student, content_version=cv)
    }
    # version-aware (v2) : la complétion est rattachée à content_version (cf. migration 0006).
    story_done = StoryAttempt.objects.filter(student=student, content_version=cv).exists()
    exam_passed = ExamAttempt.objects.filter(
        student=student, content_version=cv, passed=True
    ).exists()

    # 1. Nœuds quiz (un par concept)
    raw = []
    for c in concepts:
        cid = str(c.get('id', ''))
        passes = max(1, int(c.get('passes', 1)))
        passes_done = min(int(cprog.get(cid, 0)), passes)
        raw.append({
            'type': 'quiz',
            'title': c.get('name', cid),
            'desc': '',
            'passes': passes,
            'passes_done': passes_done,
            'is_done': passes_done >= passes,
            'xp': 20,
            'concept_id': cid,
            'url_lecteur': url_lecteur,
            'url_quiz': reverse('learn:quiz-v2',
                                kwargs={'lesson_id': cv.lesson_id, 'concept_id': cid}),
            'url_story': None,
            'url_exam': None,
        })

    # 2. Nœud story — intercalé juste avant l'exam (spec §3.4)
    if has_story:
        scene_name = 'Histoire interactive'
        if isinstance(cv.story_data, dict):
            scene_name = (cv.story_data.get('scene') or {}).get('name') or scene_name
        raw.append({
            'type': 'story',
            'title': scene_name,
            'desc': "Plonge dans l'histoire interactive",
            'passes': 1,
            'passes_done': 1 if story_done else 0,
            'is_done': story_done,
            'xp': 25,
            'concept_id': None,
            'url_lecteur': None,
            'url_quiz': None,
            'url_story': reverse('learn:story-v2', kwargs={'lesson_id': cv.lesson_id}),
            'url_exam': None,
        })

    # 3. Nœud checkpoint (exam) — toujours en dernier
    if has_exam:
        raw.append({
            'type': 'checkpoint',
            'title': 'Examen final',
            'desc': "Évalue toutes tes connaissances",
            'passes': 1,
            'passes_done': 1 if exam_passed else 0,
            'is_done': exam_passed,
            'xp': 90,
            'concept_id': None,
            'url_lecteur': None,
            'url_quiz': None,
            'url_story': None,
            'url_exam': reverse('learn:exam-v2', kwargs={'lesson_id': cv.lesson_id}),
        })

    # 4. Calcul des statuts séquentiels
    first_non_done = next((i for i, r in enumerate(raw) if not r['is_done']), len(raw))

    nodes = []
    for i, r in enumerate(raw):
        if r['is_done']:
            status = 'done'
        elif i == first_non_done:
            status = 'current'
        else:
            status = 'locked'

        t = _PCRS_TYPE[r['type']]
        passes, passes_done = r['passes'], r['passes_done']
        show_ring = (status == 'current' and r['type'] == 'quiz' and passes >= 2)
        ring = None
        if show_ring:
            track, fill, cap = _pcrs_ring_dash(passes, passes_done)
            ring = {'track': track, 'fill': fill, 'cap': cap, 'accent': t['g0']}

        nodes.append({
            'i': i,
            'type': r['type'],
            'title': r['title'],
            'desc': r['desc'],
            'status': status,
            'xp': r['xp'],
            'passes': passes,
            'passes_done': passes_done,
            'x': _pcrs_px(i),
            'y': _pcrs_py(i),
            'show_ring': show_ring,
            'ring': ring,
            'concept_id': r['concept_id'],
            'url_lecteur': r['url_lecteur'],
            'url_quiz': r['url_quiz'],
            'url_story': r.get('url_story'),
            'url_exam': r.get('url_exam'),
            **t,
        })

    return nodes


def assemble_subject_parcours(lessons, student):
    """Empile TOUTES les leçons d'une matière en un seul parcours (multi-leçons).

    Pour chaque leçon : ses nœuds via assemble_nodes (statut séquentiel INTERNE →
    déblocage INDÉPENDANT entre leçons). Entre deux leçons : un SÉPARATEUR portant
    le titre de la leçon suivante (pas avant la 1ʳᵉ). Le zigzag (x) CONTINUE à
    travers les leçons (compteur de squircles `si`) ; le y avance d'une rangée par
    nœud ET par séparateur (compteur `ri`).

    Retourne (nodes, separators) :
      nodes      — squircles avec x/y/i globaux + lesson_id/lesson_title (scroll §3)
      separators — [{title, y, lesson_id}] pour les dividers entre leçons
    """
    nodes_out, separators_out = [], []
    si = 0   # index squircle (zigzag x — continu)
    ri = 0   # index rangée (y — nœuds + séparateurs)
    for li, lesson in enumerate(lessons):
        cv = lesson.active_content_version or (
            LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
        if not cv:
            continue
        if li > 0:   # séparateur AVANT la leçon (jamais avant la 1ʳᵉ) — avec de l'air autour
            separators_out.append({      # séparateur CENTRÉ entre les 2 leçons (le +54px du .lsep tombe au milieu)
                'title': lesson.title,
                'y': _pcrs_py(ri),
                'lesson_id': lesson.id,
            })
            ri += 2                      # ~3 rangées de gap → titre pile au milieu des 2 nœuds
        for n in assemble_nodes(cv, student):
            n['x'] = _pcrs_px(si)
            n['y'] = _pcrs_py(ri)
            n['i'] = len(nodes_out)            # index global (openSheet)
            n['lesson_id'] = lesson.id
            n['lesson_title'] = lesson.title
            nodes_out.append(n)
            si += 1
            ri += 1
    return nodes_out, separators_out, ri


def _student_v2_subjects(student):
    """Matières DISTINCTES de l'élève (pour le dropdown du parcours). Une entrée par
    matière : {subject, color, url} où url = parcours de la 1ʳᵉ leçon de la matière."""
    out, seen = [], set()
    for l in _student_v2_lessons(student):   # déjà ordonné (matière, date)
        subj = l['subject'] or 'Autre'
        if subj in seen:
            continue
        seen.add(subj)
        out.append({'subject': subj, 'color': l['color'], 'url': l['url']})
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, écran LIRE / Lecteur (Phase C).
# Helpers de rendu du texte (glossaire cliquable + TTS), partagés par learn_lecteur_v2.
# ═══════════════════════════════════════════════════════════════════════════════
import re as _re
from html import escape as _esc


def _reader_rich(text, term_keys):
    """Port de rich() : enveloppe les termes du glossaire dans des boutons cliquables
    (@click Alpine openTerm). Le reste du texte est échappé (sûr)."""
    if not term_keys:
        return _esc(text)
    pattern = _re.compile('(' + '|'.join(_re.escape(k) for k in term_keys) + ')', _re.IGNORECASE)
    lower = {k.lower() for k in term_keys}
    out = []
    for part in pattern.split(text):
        if part and part.lower() in lower:
            arg = part.replace('\\', '\\\\').replace("'", "\\'")
            out.append(f'<button type="button" class="rterm" @click="openTerm(\'{arg}\')">{_esc(part)}</button>')
        else:
            out.append(_esc(part))
    return ''.join(out)


def _reader_txt_of(b):
    """Port de txtOf() : texte lu à voix haute (TTS) selon le type de bloc."""
    if b['type'] == 'p':
        return b['text']
    if b['type'] == 'def':
        return b['term'] + ". " + b['text']
    if b['type'] == 'example':
        return b['text']
    if b['type'] == 'key':
        return ". ".join(b['items'])
    return None


# ─── Vues RÉELLES v2 (données de production, élève authentifié) ───────────────

@student_required
def learn_parcours_v2(request, lesson_id):
    """Parcours v2 sur vraies données. Gated : élève authentifié + leçon déployée dans sa classe."""
    student = request.student
    lesson = get_object_or_404(
        Lesson.objects.select_related('active_content_version'),
        pk=lesson_id, format_version=2,
    )
    get_object_or_404(LessonDeployment, lesson=lesson, school_class=student.school_class, is_active=True)

    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    if not cv:
        from django.http import Http404
        raise Http404('Aucun contenu disponible.')

    # Le parcours est PAR MATIÈRE : on dérive la matière de la leçon de l'URL et on
    # empile TOUTES les leçons v2 actives de cette matière (déblocage indépendant).
    subject = lesson.subject or ''
    subject_deps = (
        LessonDeployment.objects
        .filter(school_class=student.school_class, is_active=True,
                lesson__status=LessonStatus.READY, lesson__format_version=2,
                lesson__subject=subject)
        .select_related('lesson', 'lesson__active_content_version')
        .order_by('lesson__created_at')
    )
    subject_lessons = [d.lesson for d in subject_deps] or [lesson]

    nodes, separators, total_rows = assemble_subject_parcours(subject_lessons, student)
    done_count = sum(1 for n in nodes if n['status'] == 'done')
    progress_ratio = round(done_count / len(nodes), 4) if nodes else 0

    segments = []
    for i in range(len(nodes) - 1):
        p, q = nodes[i], nodes[i + 1]
        my = (p['y'] + q['y']) / 2
        segments.append({
            'd': f"M {p['x']} {p['y']} C {p['x']} {my}, {q['x']} {my}, {q['x']} {q['y']}",
            'lit': p['status'] == 'done',
        })

    # Dropdown = UNIQUEMENT des matières (jamais des titres de leçon).
    # Couleur = teinte de matière AUTO (par position → distinct dans la classe).
    from apps.student_learning.theme import subject_hue_at
    subjects = _student_v2_subjects(student)
    cur_name = subject or 'Autre'
    names = [s['subject'] for s in subjects]
    hue = subject_hue_at(names.index(cur_name)) if cur_name in names else subject_hue_at(0)
    for i, s in enumerate(subjects):
        s['current'] = (s['subject'] == cur_name)
        s['hue'] = subject_hue_at(i)
    # Teinte par nœud : matière pour quiz/histoire, OR pour l'examen (couronne).
    for n in nodes:
        n['hue'] = 'amber' if n['type'] == 'checkpoint' else hue

    head_color = cv.color or '#818CF8'
    return render(request, 'student_learning/parcours_v2.html', {
        'hue':            hue,
        'lesson': {
            'title':  subject_lessons[0].title,   # titre de la 1ʳᵉ leçon (scroll-driven en §3)
            'subject': subject,
            'color':  head_color,
            'guide':  cv.guide or '',
        },
        'nodes':          nodes,
        'separators':     separators,
        'segments':       segments,
        'canvas_h':       total_rows * _PCRS_ROW_H + 60,
        'col_w':          _PCRS_COL_W,
        'node_size':      _PCRS_NODE,
        'progress_ratio': progress_ratio,
        'subjects':       subjects,
        'lecteur_url':    reverse('learn:lecteur-v2', kwargs={'lesson_id': subject_lessons[0].id}),
        'first_lesson_id': subject_lessons[0].id,
    })


@student_required
def learn_lecteur_v2(request, lesson_id):
    """Lecteur v2 sur vraies données (reading_data). Gated : élève authentifié + leçon déployée."""
    student = request.student
    lesson = get_object_or_404(
        Lesson.objects.select_related('active_content_version'),
        pk=lesson_id, format_version=2,
    )
    get_object_or_404(LessonDeployment, lesson=lesson, school_class=student.school_class, is_active=True)

    cv = lesson.active_content_version
    if not cv:
        cv = (LessonContentVersion.objects
              .filter(lesson=lesson).order_by('-version').first())
    if not cv or not cv.reading_data:
        from django.http import Http404
        raise Http404('Aucun contenu de lecture disponible.')

    rd = cv.reading_data
    term_keys = list((rd.get('terms') or {}).keys())

    sections = []
    tts = []
    for si, s in enumerate(rd.get('sections', [])):
        blocks = []
        sec_tts = []
        for bi, b in enumerate(s.get('blocks', [])):
            nb = dict(b, si=si, bi=bi)
            if b.get('type') == 'p':
                nb['rich_html'] = _reader_rich(b.get('text', ''), term_keys)
            blocks.append(nb)
            t = _reader_txt_of(b)
            if t:
                sec_tts.append({'bi': bi, 'text': t})
        sections.append({'id': s.get('id', f's{si}'), 'title': s.get('title', ''), 'blocks': blocks})
        tts.append(sec_tts)

    subject = lesson.subject or ''
    # Teinte de matière AUTO (par position) — MÊME calcul que le parcours, pour que
    # la même matière ait la même couleur partout (parcours ↔ lecteur).
    from apps.student_learning.theme import subject_hue_at
    _subjects = _student_v2_subjects(student)
    _names = [s['subject'] for s in _subjects]
    _cur = subject or 'Autre'
    hue = subject_hue_at(_names.index(_cur)) if _cur in _names else subject_hue_at(0)

    # Notes perso persistées (par leçon → survivent aux régénérations de contenu).
    notes = [
        {'id': n.id, 'section': n.section, 'text': n.text}
        for n in StudentNote.objects.filter(student=student, lesson=lesson)
    ]

    return render(request, 'student_learning/lecteur_v2.html', {
        'hue':     hue,
        'notes_json':   notes,
        'note_add_url': reverse('learn:note-v2-add', kwargs={'lesson_id': lesson_id}),
        'note_del_url': reverse('learn:note-v2-delete', kwargs={'lesson_id': lesson_id}),
        'lesson': {
            'title':   lesson.title,
            'subject': subject,
            'color':   cv.color or '#818CF8',
        },
        'subject_short':   subject.split('—')[0].strip() if '—' in subject else subject,
        'reading_title':   rd.get('title', lesson.title),
        'sections':        sections,
        'section_titles':  [s.get('title', '') for s in rd.get('sections', [])],
        'terms':           rd.get('terms') or {},
        'tts':             tts,
        'n_sections':      len(sections),
        'back_url':        reverse('learn:parcours-v2', kwargs={'lesson_id': lesson_id}),
    })


@student_required
@require_http_methods(['POST'])
def note_v2_add(request, lesson_id):
    """Crée une note perso de lecture (persistée). Retourne la note créée."""
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id, format_version=2)
    get_object_or_404(LessonDeployment, lesson=lesson,
                      school_class=student.school_class, is_active=True)
    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    try:
        data = json.loads(request.body)
        text = (data.get('text') or '').strip()[:2000]
        section = (data.get('section') or '').strip()[:200]
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid'}, status=400)
    if not text:
        return JsonResponse({'error': 'Vide'}, status=400)

    note = StudentNote.objects.create(
        student=student, lesson=lesson, content_version=cv,
        section=section, text=text,
    )
    return JsonResponse({'id': note.id, 'section': note.section, 'text': note.text})


@student_required
@require_http_methods(['POST'])
def note_v2_delete(request, lesson_id):
    """Supprime une note perso (uniquement si elle appartient à l'élève)."""
    student = request.student
    try:
        note_id = int(json.loads(request.body).get('id'))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid'}, status=400)
    StudentNote.objects.filter(id=note_id, student=student, lesson_id=lesson_id).delete()
    return JsonResponse({'ok': True})


# ─── STORY v2 RÉELLE (étape 4) — player immersif sur story_data réel ──────────
# Éval CÔTÉ CLIENT (à la designer : choice/input/tokens/blank) — moment plaisir,
# pas d'enjeu anti-triche. Seule la complétion (score) est persistée côté serveur.

@student_required
def learn_story_v2(request, lesson_id):
    """Affiche la VRAIE story (story_data) dans le player immersif (gated)."""
    student = request.student
    lesson = get_object_or_404(
        Lesson.objects.select_related('active_content_version'),
        pk=lesson_id, format_version=2,
    )
    get_object_or_404(LessonDeployment, lesson=lesson,
                      school_class=student.school_class, is_active=True)
    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    if not cv or not cv.story_data:
        raise Http404('Aucune histoire disponible.')

    sd = cv.story_data
    _name = (student.first_name or student.full_name or '').strip()
    return render(request, 'student_learning/story_v2.html', {
        'lesson': {'title': lesson.title, 'subject': lesson.subject or '',
                   'color': cv.color or '#10B981'},
        'scene':        sd.get('scene') or {},
        'characters':   sd.get('characters') or [],
        'steps':        sd.get('steps') or [],
        'student_first': _name.split()[0] if _name else '',
        'finish_url':   reverse('learn:story-v2-finish', kwargs={'lesson_id': lesson_id}),
        'parcours_url': reverse('learn:parcours-v2', kwargs={'lesson_id': lesson_id}),
    })


@student_required
@require_http_methods(['POST'])
def story_v2_finish(request, lesson_id):
    """Enregistre la complétion de la story (version-aware) → débloque le nœud suivant."""
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id, format_version=2)
    get_object_or_404(LessonDeployment, lesson=lesson,
                      school_class=student.school_class, is_active=True)
    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    if not cv:
        return JsonResponse({'error': 'Aucun contenu'}, status=404)

    try:
        data = json.loads(request.body)
        score = max(0, min(100, int(data.get('score', 0))))
        answers = data.get('answers', [])
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid'}, status=400)

    first_time = not StoryAttempt.objects.filter(
        student=student, content_version=cv).exists()
    StoryAttempt.objects.create(
        student=student, lesson=lesson, content_version=cv,
        score=score, answers=answers if isinstance(answers, list) else [],
    )
    return JsonResponse({'ok': True, 'first_time': first_time})


# ─── EXAM v2 RÉEL (étape 5) — "Le Sommet" : 4 phases, SOMMATIF, correction SERVEUR ─
# Aucun feedback pendant l'épreuve ; correction de TOUTES les réponses au submit via
# evaluate_answer_v2 ; réponses correctes jamais exposées avant soumission. Dernier
# maillon : exam passé → checkpoint "done" → parcours complété.

def _concept_name_map(cv):
    """{concept_id: nom} depuis concepts_data — pour le bilan par notion."""
    concepts = cv.concepts_data if isinstance(cv.concepts_data, list) else []
    return {str(c.get('id', '')): c.get('name', c.get('id', '')) for c in concepts}


@student_required
def learn_exam_v2(request, lesson_id):
    """Affiche l'exam réel (exam_data) dans le player 'Le Sommet' (gated).
    Questions masquées (réponses jamais envoyées au client avant soumission)."""
    student = request.student
    lesson = get_object_or_404(
        Lesson.objects.select_related('active_content_version'),
        pk=lesson_id, format_version=2,
    )
    get_object_or_404(LessonDeployment, lesson=lesson,
                      school_class=student.school_class, is_active=True)
    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    if not cv or not cv.exam_data:
        raise Http404('Aucun examen disponible.')

    ed = cv.exam_data
    names = _concept_name_map(cv)
    questions = []
    for q in ed.get('questions', []):
        cq = _quiz_to_client(q)                      # masque les réponses + normalise (matching/cloze)
        cq['concept_id'] = q.get('concept_id', '')
        cq['concept_name'] = names.get(str(q.get('concept_id', '')), 'Notion')
        questions.append(cq)

    from apps.student_learning.theme import subject_hue_at
    _subjects = _student_v2_subjects(student)
    _names = [s['subject'] for s in _subjects]
    _cur = lesson.subject or 'Autre'
    hue = subject_hue_at(_names.index(_cur)) if _cur in _names else subject_hue_at(0)

    return render(request, 'student_learning/exam_runner_v2.html', {
        'hue': hue,
        'lesson': {'title': lesson.title, 'subject': lesson.subject or '',
                   'color': cv.color or '#818CF8'},
        'meta': {
            'title': "Examen final",
            'duration_s': int(ed.get('duration', 600)),
            'pass_mark': float(ed.get('pass_mark', 0.6)),
        },
        'questions':    questions,
        'n_questions':  len(questions),
        'submit_url':   reverse('learn:exam-v2-submit', kwargs={'lesson_id': lesson_id}),
        'parcours_url': reverse('learn:parcours-v2', kwargs={'lesson_id': lesson_id}),
    })


@student_required
@require_http_methods(['POST'])
def exam_v2_submit(request, lesson_id):
    """Corrige TOUT côté serveur (evaluate_answer_v2), crée l'ExamAttempt, renvoie le
    bilan (score, passed, par notion, détail par question avec la solution révélée)."""
    from apps.lessons.services import evaluate_answer_v2
    student = request.student
    lesson = get_object_or_404(Lesson, pk=lesson_id, format_version=2)
    get_object_or_404(LessonDeployment, lesson=lesson,
                      school_class=student.school_class, is_active=True)
    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    if not cv or not cv.exam_data:
        return JsonResponse({'error': 'Aucun examen'}, status=404)

    try:
        data = json.loads(request.body)
        client_answers = data.get('answers', [])      # liste indexée par position de question
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid'}, status=400)

    ed = cv.exam_data
    questions = ed.get('questions', [])
    pass_mark = float(ed.get('pass_mark', 0.6))
    names = _concept_name_map(cv)

    # Correction question par question (100% serveur)
    details = []
    per_concept = {}   # concept_id -> [correct_count, total]
    correct_total = 0
    for i, q in enumerate(questions):
        student_answer = client_answers[i] if i < len(client_answers) else None
        is_correct = bool(evaluate_answer_v2(q, student_answer))
        correct_total += 1 if is_correct else 0
        cid = str(q.get('concept_id', ''))
        agg = per_concept.setdefault(cid, [0, 0])
        agg[0] += 1 if is_correct else 0
        agg[1] += 1
        details.append({
            'i': i,
            'concept_id': cid,
            'concept_name': names.get(cid, 'Notion'),
            'type': q.get('type', ''),
            'instruction': q.get('instruction', ''),
            'student_answer': student_answer,
            'correct': is_correct,
            'solution': _quiz_solution(q),            # révélée SEULEMENT maintenant
            'explanation': q.get('explanation', ''),
        })

    total = len(questions) or 1
    score = correct_total / total
    passed = score >= pass_mark

    concepts = [{
        'id': cid, 'name': names.get(cid, 'Notion'),
        'correct': c, 'total': t, 'pct': round(c / t * 100) if t else 0,
    } for cid, (c, t) in per_concept.items()]

    attempt_number = ExamAttempt.objects.filter(
        student=student, content_version=cv).count() + 1
    ExamAttempt.objects.create(
        student=student, lesson=lesson, content_version=cv,
        attempt_number=attempt_number, pass_mark=pass_mark,
        score=score, passed=passed,
        answers={'details': details, 'concepts': concepts},
        submitted_at=timezone.now(),
    )

    return JsonResponse({
        'score_pct': round(score * 100),
        'passed': passed,
        'pass_mark_pct': round(pass_mark * 100),
        'correct': correct_total, 'total': total,
        'concepts': concepts,
        'questions': details,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# QUIZ v2 RÉEL (étape 3) — affichage des vrais quiz d'un concept + VALIDATION
# SERVEUR (evaluate_answer_v2) + persistance (QuizAttempt → ConceptProgress).
# Principe sécurité (§A.5) : la réponse correcte ne transite JAMAIS vers le client
# avant soumission ; le verdict vient du serveur. Prépare le terrain dynamic_formula.
# ═══════════════════════════════════════════════════════════════════════════════

# Champs-réponse à NE JAMAIS exposer au client tant que la réponse n'est pas soumise.
_QUIZ_ANSWER_FIELDS = (
    'answer_index', 'answer_indices', 'answer', 'odd_index', 'answers',
    'correct_order', 'buggy_line', 'correct_fix', 'pairs', 'solution_formula',
    'tolerance', 'variables',
    # types restants : la séquence/expression correcte ne doit jamais partir au client.
    'correct_sequence', 'correct_expression', 'accepted_equivalents',
    # explanation peut révéler la réponse → jamais côté client ; le feedback la
    # reçoit du serveur (réponse JSON de quiz_v2_answer).
    'explanation',
)


def _quiz_to_client(quiz):
    """Copie d'un quiz SANS les champs-réponse — sûre à envoyer au client.

    Tout le reste (instruction, options, items, text…) est conservé pour le rendu.
    Cas spéciaux :
      - k_prime        : les statements gardent `text`, perdent `answer`.
      - matching       : `pairs` (l'adjacence left↔right EST la réponse) est strippé ;
        on envoie les `lefts` ordonnés + les `rights` MÉLANGÉS, chacun gardant son
        index d'origine `oi` (réponse[i] = oi du right choisi pour left[i]).
      - parsons_puzzle : chaque ligne garde `id`+`text`, PERD `correct_indent` (réponse).
    Note : dynamic_formula est traité dans la vue (énoncé tiré côté serveur) — ici on
    se contente de retirer variables/solution_formula (déjà dans la liste).
    Réutilisable pour tous les concepts ; le serveur garde le quiz complet."""
    out = {k: v for k, v in quiz.items() if k not in _QUIZ_ANSWER_FIELDS}
    t = quiz.get('type')
    if t == 'k_prime':
        out['statements'] = [{'text': s.get('text', '')} for s in quiz.get('statements', [])]
    elif t == 'matching':
        import random as _random
        pairs = quiz.get('pairs', [])
        out['lefts'] = [p.get('left', '') for p in pairs]
        rights = [{'text': p.get('right', ''), 'oi': i} for i, p in enumerate(pairs)]
        _random.shuffle(rights)
        out['rights'] = rights
    elif t == 'parsons_puzzle':
        import random as _random
        lines = [{'id': l.get('id'), 'text': l.get('text', '')} for l in quiz.get('lines', [])]
        _random.shuffle(lines)   # mélange l'ordre de départ (sinon la séquence serait donnée)
        out['lines'] = lines
    return out


def _quiz_solution(quiz, context=None):
    """Réponse correcte minimale, renvoyée APRÈS validation pour rendre le feedback
    (surlignage / correction). Jamais exposée avant soumission.

    `context` = {'variables': …} pour dynamic_formula (recalcul de la bonne réponse
    depuis le tirage serveur). Ignoré par les autres types."""
    t = quiz.get('type')
    if t == 'mcq_single':   return {'answer_index': quiz.get('answer_index')}
    if t == 'mcq_multiple': return {'answer_indices': quiz.get('answer_indices', [])}
    if t == 'true_false':   return {'answer': bool(quiz.get('answer'))}
    if t == 'odd_one_out':  return {'odd_index': quiz.get('odd_index')}
    if t == 'k_prime':      return {'answers': [bool(s.get('answer')) for s in quiz.get('statements', [])]}
    if t == 'cloze_test':   return {'answers': quiz.get('answers', [])}
    # matching : la bonne association left[i] → right d'origine i (paires ordonnées).
    if t == 'matching':     return {'pairs': quiz.get('pairs', [])}
    if t == 'chrono_order': return {'correct_order': quiz.get('correct_order', [])}
    if t == 'number_input': return {'answer': quiz.get('answer'), 'unit': quiz.get('unit', '')}
    if t == 'spot_the_bug': return {'buggy_line': quiz.get('buggy_line'), 'correct_fix': quiz.get('correct_fix', '')}
    if t == 'math_expression': return {'correct_expression': quiz.get('correct_expression', '')}
    if t == 'parsons_puzzle':
        # séquence + indentation correctes, dans l'ordre, pour afficher la solution.
        by_id = {l.get('id'): l for l in quiz.get('lines', [])}
        seq = quiz.get('correct_sequence', [])
        return {'sequence': [{'text': by_id.get(i, {}).get('text', ''),
                              'indent': by_id.get(i, {}).get('correct_indent', 0)} for i in seq]}
    if t == 'dynamic_formula':
        from apps.lessons.services import _safe_eval_arith
        if isinstance(context, dict) and 'variables' in context:
            try:
                ans = _safe_eval_arith(quiz.get('solution_formula', '0'), context['variables'])
                return {'answer': ans, 'unit': quiz.get('unit', '')}
            except Exception:
                return {'unit': quiz.get('unit', '')}
        return {'unit': quiz.get('unit', '')}
    return {}


def _concept_passes(concept):
    """Nombre de passes déclarés du concept (1..4), borné défensivement."""
    return max(1, int(concept.get('passes', 1)))


def _recompute_concept_progress(student, cv, concept):
    """Recalcule passes_done depuis les QuizAttempt (SOURCE DE VÉRITÉ, §3.4).

    Règle : un pass est *maîtrisé* quand CHAQUE quiz de ce pass a ≥1 QuizAttempt
    correct de l'élève (formatif, basé maîtrise). passes_done = nombre de passes
    consécutifs maîtrisés depuis le pass 0 (déblocage séquentiel). Idempotent."""
    quizzes = concept.get('quiz', [])
    passes = _concept_passes(concept)

    correct_ids = set(
        QuizAttempt.objects
        .filter(student=student, content_version=cv, is_correct=True,
                quiz_id__in=[str(q.get('id')) for q in quizzes])
        .values_list('quiz_id', flat=True)
    )

    passes_done = 0
    for p in range(passes):
        pass_quizzes = [q for q in quizzes if int(q.get('pass_index', 0)) == p]
        if pass_quizzes and all(str(q.get('id')) in correct_ids for q in pass_quizzes):
            passes_done += 1
        else:
            break  # séquentiel : on s'arrête au premier pass non maîtrisé

    ConceptProgress.objects.update_or_create(
        student=student, content_version=cv, concept_id=str(concept.get('id', '')),
        defaults={'lesson_id': cv.lesson_id, 'passes_done': passes_done},
    )
    return passes_done


def _v2_concept_or_404(student, lesson_id, concept_id):
    """Charge (lesson, cv, concept) pour un élève AUTORISÉ (leçon v2 déployée dans
    sa classe). 404 sinon. Brique commune affichage + validation."""
    lesson = get_object_or_404(
        Lesson.objects.select_related('active_content_version'),
        pk=lesson_id, format_version=2,
    )
    get_object_or_404(LessonDeployment, lesson=lesson,
                      school_class=student.school_class, is_active=True)
    cv = lesson.active_content_version or (
        LessonContentVersion.objects.filter(lesson=lesson).order_by('-version').first())
    if not cv:
        raise Http404('Aucun contenu disponible.')
    concepts = cv.concepts_data if isinstance(cv.concepts_data, list) else []
    concept = next((c for c in concepts if str(c.get('id', '')) == str(concept_id)), None)
    if concept is None:
        raise Http404('Concept introuvable.')
    return lesson, cv, concept


@student_required
def learn_quiz_v2(request, lesson_id, concept_id):
    """Affiche les quiz du PASS COURANT d'un concept (vraies données, gated).

    Le pass joué = le pass courant (= passes_done) ; si le concept est terminé,
    on rejoue le dernier pass (révision, sans incrément possible)."""
    student = request.student
    lesson, cv, concept = _v2_concept_or_404(student, lesson_id, concept_id)

    passes = _concept_passes(concept)
    done = (ConceptProgress.objects
            .filter(student=student, content_version=cv, concept_id=str(concept_id))
            .values_list('passes_done', flat=True).first()) or 0
    pass_to_play = done if done < passes else passes - 1

    quizzes = [q for q in concept.get('quiz', [])
               if int(q.get('pass_index', 0)) == pass_to_play]

    # dynamic_formula : tirage des variables CÔTÉ SERVEUR (anti-triche A.5). Le client
    # ne reçoit que l'énoncé chiffré ; variables + solution restent serveur (QuestionDraw).
    from apps.lessons.services import draw_dynamic_formula
    client_quizzes = []
    for q in quizzes:
        cq = _quiz_to_client(q)
        if q.get('type') == 'dynamic_formula':
            drawn = draw_dynamic_formula(q)
            # practice (exam_attempt=None) : on remplace le tirage précédent → re-tirage à chaque ouverture
            QuestionDraw.objects.filter(student=student, content_version=cv,
                                        quiz_id=str(q.get('id')), exam_attempt__isnull=True).delete()
            QuestionDraw.objects.create(student=student, content_version=cv,
                                        quiz_id=str(q.get('id')), variables=drawn['variables'])
            cq['instruction'] = drawn['statement']   # énoncé avec valeurs substituées
        client_quizzes.append(cq)

    # Teinte de matière AUTO (par position) — même calcul que parcours/lecteur.
    from apps.student_learning.theme import subject_hue_at
    _subjects = _student_v2_subjects(student)
    _names = [s['subject'] for s in _subjects]
    _cur = lesson.subject or 'Autre'
    hue = subject_hue_at(_names.index(_cur)) if _cur in _names else subject_hue_at(0)

    return render(request, 'student_learning/quiz_runner_v2.html', {
        'hue': hue,
        'lesson': {'title': lesson.title, 'subject': lesson.subject or '',
                   'color': cv.color or '#818CF8'},
        'concept': {'id': str(concept_id), 'name': concept.get('name', '')},
        'pass_index':   pass_to_play,
        'passes':       passes,
        'questions':    client_quizzes,
        'n_questions':  len(client_quizzes),
        'answer_url':   reverse('learn:quiz-v2-answer',
                                kwargs={'lesson_id': lesson_id, 'concept_id': concept_id}),
        'parcours_url': reverse('learn:parcours-v2', kwargs={'lesson_id': lesson_id}),
    })


@student_required
@require_http_methods(['POST'])
def quiz_v2_answer(request, lesson_id, concept_id):
    """Valide UNE réponse côté serveur (evaluate_answer_v2), enregistre la
    QuizAttempt, recalcule ConceptProgress. Renvoie verdict + explication +
    solution (la solution n'est exposée qu'APRÈS soumission)."""
    from apps.lessons.services import evaluate_answer_v2
    student = request.student
    lesson, cv, concept = _v2_concept_or_404(student, lesson_id, concept_id)

    try:
        data = json.loads(request.body)
        quiz_id = str(data.get('quiz_id', ''))
        student_answer = data.get('answer')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid'}, status=400)

    quiz = next((q for q in concept.get('quiz', []) if str(q.get('id')) == quiz_id), None)
    if quiz is None:
        return JsonResponse({'error': 'Quiz introuvable'}, status=404)

    # dynamic_formula : on relit le tirage SERVEUR (jamais reçu du client) et on
    # recalcule la réponse attendue avec ces variables (anti-triche A.5).
    context = None
    draw_variables = None
    if quiz.get('type') == 'dynamic_formula':
        draw = (QuestionDraw.objects
                .filter(student=student, content_version=cv, quiz_id=quiz_id,
                        exam_attempt__isnull=True)
                .order_by('-created_at').first())
        if draw:
            context = {'variables': draw.variables}
            draw_variables = draw.variables

    is_correct = bool(evaluate_answer_v2(quiz, student_answer, context))

    QuizAttempt.objects.create(
        student=student, lesson=lesson, content_version=cv,
        quiz_id=quiz_id, question_type=quiz.get('type', ''),
        student_answer=student_answer, is_correct=is_correct,
        draw_variables=draw_variables,
    )
    passes_done = _recompute_concept_progress(student, cv, concept)

    return JsonResponse({
        'correct':     is_correct,
        'explanation': quiz.get('explanation', ''),
        'solution':    _quiz_solution(quiz, context),
        'passes_done': passes_done,
        'passes':      _concept_passes(concept),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Révision (répétition espacée) — l'onglet qui s'allume. Logique dans srs.py ;
# ici : la page « Ma révision », la session (réutilise le runner de quiz) et la
# validation. Application des boîtes AU FIL DE L'EAU : dès que les 2 questions
# d'un concept sont répondues, sa boîte bouge (quitter en cours ne perd rien).
# ═══════════════════════════════════════════════════════════════════════════════

def _fr_day_label(d):
    """Libellé français court d'une date à venir : Demain, sinon jour de semaine."""
    from django.utils import timezone as _tz
    today = _tz.localdate()
    if d == today + timedelta(days=1):
        return 'Demain'
    days = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    return days[d.weekday()]


@student_required
def learn_revision(request):
    """Page « Ma révision » : sync + file du jour, ou état « tout est frais »."""
    from . import srs
    from .theme import subject_hue_at
    student = request.student

    srs.sync_reviews(student)
    queue = srs.today_queue(student)

    # teinte par matière — même calcul par POSITION que parcours/quiz (repère).
    subject_names = [s['subject'] for s in _student_v2_subjects(student)]
    def _hue(subject):
        return (subject_hue_at(subject_names.index(subject))
                if subject in subject_names else subject_hue_at(0))

    items = [{
        'name': i['name'],
        'subject': i['subject'] or 'Autre',
        'lesson_title': i['lesson_title'],
        'box': i['box'],
        'state': i['state'],
        'late_days': i['late_days'],
        'tomorrow_time': i['tomorrow_time'],
        'hue': _hue(i['subject']),
        'letter': (i['subject'] or 'A')[:1].upper(),
    } for i in queue]

    _name = (student.first_name or student.full_name or '').strip()
    return render(request, 'student_learning/revision_v2.html', {
        'student': student,
        'student_first': _name.split()[0] if _name else '',
        'items': items,
        'est_minutes': max(2, round(len(items) * 1.4)),
        'garden': srs.garden_counts(student),
        'next_days': [{'label': _fr_day_label(g['date']), 'count': g['count'],
                       'subjects': g['subjects'][:2]} for g in srs.next_days_preview(student)],
        'session_count': len(items),     # taille de la session (CTA)
        'due_total': srs.due_count(student),   # total mûrs (en-tête, cohérent pastille)
    })


@student_required
def revision_session(request):
    """Construit la session du jour : 2 questions par concept mûr, tirées au
    hasard dans la réserve du concept (types mélangés), puis ENTRELACÉES entre
    concepts (interleaving). Servie par le runner de quiz en mode révision.
    Le mapping question→concept reste CÔTÉ SERVEUR (session Django)."""
    import random
    from apps.lessons.services import draw_dynamic_formula
    from . import srs
    student = request.student

    srs.sync_reviews(student)
    queue = srs.today_queue(student)
    if not queue:
        return redirect('learn:revision')

    questions, items = [], {}
    for item in queue:
        pool = [q for q in item['concept'].get('quiz', []) if q.get('id')]
        if not pool:      # concept sans quiz (contenu IA incomplet) → on saute
            continue
        picks = random.sample(pool, min(srs.QUESTIONS_PER_CONCEPT, len(pool)))
        for q in picks:
            cv = item['review'].content_version
            sid = f"r{item['review'].id}:{q.get('id')}"
            cq = _quiz_to_client(q)
            cq['id'] = sid   # id de session UNIQUE (2 leçons peuvent partager 'q1')
            if q.get('type') == 'dynamic_formula':
                drawn = draw_dynamic_formula(q)
                QuestionDraw.objects.filter(student=student, content_version=cv,
                                            quiz_id=str(q.get('id')),
                                            exam_attempt__isnull=True).delete()
                QuestionDraw.objects.create(student=student, content_version=cv,
                                            quiz_id=str(q.get('id')),
                                            variables=drawn['variables'])
                cq['instruction'] = drawn['statement']
            questions.append(cq)
            items[sid] = {'review_id': item['review'].id,
                          'quiz_id': str(q.get('id')), 'correct': None}
    if not questions:
        return redirect('learn:revision')
    random.shuffle(questions)

    request.session['srs_session'] = {'items': items, 'applied': []}

    return render(request, 'student_learning/quiz_runner_v2.html', {
        'mode': 'revision',
        'hue': 'coral',   # la révision est TRANSVERSALE → couleur de marque
        'lesson': {'title': 'Révision du jour', 'subject': 'Révision',
                   'color': '#FF7A59'},
        'concept': {'id': 'revision', 'name': 'Révision du jour'},
        'pass_index': 0,
        'passes': 1,
        'questions': questions,
        'n_questions': len(questions),
        'answer_url': reverse('learn:revision-answer'),
        'parcours_url': reverse('learn:revision'),
    })


@student_required
@require_http_methods(['POST'])
def revision_answer(request):
    """Valide UNE réponse de révision (moteur serveur identique au quiz).
    Quand les questions d'un concept sont toutes répondues, applique le
    mouvement de boîte UNE seule fois et le renvoie (bilan côté client)."""
    from apps.lessons.services import evaluate_answer_v2
    from . import srs
    from .models import ConceptReview
    student = request.student

    try:
        data = json.loads(request.body)
        sid = str(data.get('quiz_id', ''))
        student_answer = data.get('answer')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid'}, status=400)

    sess = request.session.get('srs_session') or {}
    entry = (sess.get('items') or {}).get(sid)
    if entry is None:
        return JsonResponse({'error': 'Session expirée'}, status=409)

    review = (ConceptReview.objects
              .filter(id=entry['review_id'], student=student)
              .select_related('lesson', 'content_version').first())
    if review is None:
        return JsonResponse({'error': 'Révision introuvable'}, status=404)
    cv = review.content_version
    concept = srs._concepts_map(cv).get(review.concept_id)
    quiz = None
    if concept:
        quiz = next((q for q in concept.get('quiz', [])
                     if str(q.get('id')) == entry['quiz_id']), None)
    if quiz is None:
        return JsonResponse({'error': 'Quiz introuvable'}, status=404)

    # dynamic_formula : tirage serveur relu (jamais reçu du client)
    context = None
    draw_variables = None
    if quiz.get('type') == 'dynamic_formula':
        draw = (QuestionDraw.objects
                .filter(student=student, content_version=cv,
                        quiz_id=entry['quiz_id'], exam_attempt__isnull=True)
                .order_by('-created_at').first())
        if draw:
            context = {'variables': draw.variables}
            draw_variables = draw.variables

    is_correct = bool(evaluate_answer_v2(quiz, student_answer, context))
    QuizAttempt.objects.create(
        student=student, lesson=review.lesson, content_version=cv,
        quiz_id=entry['quiz_id'], question_type=quiz.get('type', ''),
        student_answer=student_answer, is_correct=is_correct,
        draw_variables=draw_variables, source='revision',
    )

    entry['correct'] = is_correct
    move = None
    siblings = [e for e in sess['items'].values()
                if e['review_id'] == entry['review_id']]
    if (all(e['correct'] is not None for e in siblings)
            and entry['review_id'] not in sess.get('applied', [])):
        success = all(e['correct'] for e in siblings)
        old_box = review.box
        srs.apply_result(review, success)
        sess.setdefault('applied', []).append(entry['review_id'])
        move = {
            'name': (concept.get('name') or review.concept_id),
            'subject': review.lesson.subject or '',
            'up': success,
            'from_state': srs.state_of(old_box),
            'to_state': srs.state_of(review.box),
        }
    request.session['srs_session'] = sess

    return JsonResponse({
        'correct':     is_correct,
        'explanation': quiz.get('explanation', ''),
        'solution':    _quiz_solution(quiz, context),
        'move':        move,
    })


# ─── Phase 0 — Atelier du design system (styleguide dev, portail élève) ───────

def design_system(request):
    """Page-atelier « Ludique doux » : rampes, tokens sémantiques + composant,
    typo (comparateur de polices), boutons, cartes, badges, progression, la
    DÉMO DE QUIZ EN JEU (tiles + feedback + CTA pressable), et l'auto-couleur de
    20 matières — en clair ET sombre. Sert à valider le système avant les écrans.
    Sans auth : ne lit aucune donnée élève (uniquement des tokens)."""
    from apps.student_learning.theme import subject_hue_at, SUBJECT_HUES
    demo_subjects = [
        'Mathématiques', 'Français', 'Physique', 'Chimie', 'Biologie', 'Informatique',
        'Histoire', 'Géographie', 'Anglais', 'Philosophie', 'Économie', 'Comptabilité',
        'Marketing', 'Droit', 'Anatomie', 'Robotique', 'Astronomie', 'Cybersécurité',
        'Éducation civique', 'Arts plastiques',
    ]
    subjects = [{'name': s, 'hue': subject_hue_at(i)} for i, s in enumerate(demo_subjects)]
    return render(request, 'student_learning/_design_system.html', {
        'subjects': subjects,
        'hues': SUBJECT_HUES,
    })
