import json
import logging
from collections import defaultdict, OrderedDict
from datetime import timedelta
from urllib.parse import urlencode

import datetime

from django.db.models import Count, F
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.core.student_auth import (
    authenticate_student, login_student, logout_student, student_required,
)
from apps.lessons.models import Lesson, LessonContentVersion, LessonDeployment, LessonStatus
from apps.student_learning.services import student_stats, BADGES_CATALOG
from apps.student_learning.models import (
    QuizAttempt, StoryAttempt,
    ConceptProgress, ExamAttempt, QuestionDraw,
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


# ─── Profil (Phase 9) ────────────────────────────────────────────────────────

@student_required
def learn_profile(request):
    student = request.student
    return render(request, 'learn/profile.html', {
        'student': student,
        'stats': student_stats(student),
        'badges_catalog': BADGES_CATALOG,
    })


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


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, écran PARCOURS (Phase C).
# DÉMO : données en dur (mock du design code.jsx). Branchement v2 réel plus tard.
# Port Python fidèle des constantes/maths du design (px/py, anneau, chemin).
# Standalone, parallèle au v1 (/learn/ inchangé). Route : /learn/v2/parcours/.
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
_PCRS_COL_W, _PCRS_NODE, _PCRS_ROW_H, _PCRS_AMP, _PCRS_CX = 300, 74, 132, 82, 150


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
            'title': f"Quiz · {c.get('name', cid)}",
            'desc': c.get('name', cid),
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


# Mock du design (sous-ensemble couvrant tous les états : done/current/locked,
# anneaux 2/3 passes, quiz/story/checkpoint).
_PCRS_DEMO = {
    'title': "Biologie · La Cellule", 'subject': "SVT — Terminale",
    'color': "#10B981", 'guide': "Cyto",
    'raw': [
        ('quiz',       "Quiz : les bases du vivant",  "Valide les fondations de la cellule.",       'done',    20, 1, 1),
        ('story',      "Le voyage de Cyto",           "Explore une cellule de l'intérieur.",        'done',    25, 1, 0),
        ('quiz',       "Quiz : structure cellulaire", "Les grands organites et leur rôle.",         'done',    20, 2, 2),
        ('quiz',       "Quiz : le transport",         "Diffusion, osmose et transport actif.",      'current', 20, 3, 1),
        ('quiz',       "Quiz : récap transport",      "Consolide avant le grand saut.",             'locked',  20, 2, 0),
        ('checkpoint', "Mini-examen : la membrane",   "Mets-toi en condition d'examen.",            'locked',  50, 1, 0),
        ('story',      "Le code secret",              "Décrypte l'ADN dans une aventure.",          'locked',  25, 1, 0),
        ('checkpoint', "Examen final du module",      "Valide tout le module Biologie.",            'locked',  90, 1, 0),
    ],
}


def parcours_v2_demo(request):
    """Écran PARCOURS v2 (DÉMO, données en dur). Ungated (aucune donnée réelle).
    À gater/brancher sur les vraies données v2 ultérieurement."""
    d = _PCRS_DEMO
    nodes = []
    for i, (typ, title, desc, status, xp, passes, passes_done) in enumerate(d['raw']):
        t = _PCRS_TYPE[typ]
        show_ring = (status == 'current' and typ == 'quiz' and passes >= 2)
        ring = None
        if show_ring:
            track, fill, cap = _pcrs_ring_dash(passes, passes_done)
            ring = {'track': track, 'fill': fill, 'cap': cap, 'accent': t['g0']}
        nodes.append({
            'i': i, 'type': typ, 'title': title, 'desc': desc, 'status': status,
            'xp': xp, 'passes': passes, 'passes_done': passes_done,
            'x': _pcrs_px(i), 'y': _pcrs_py(i), 'show_ring': show_ring, 'ring': ring,
            **t,
        })

    # Segments du chemin ondulé (courbe de Bézier entre nœuds consécutifs).
    segments = []
    for i in range(len(nodes) - 1):
        p, q = nodes[i], nodes[i + 1]
        my = (p['y'] + q['y']) / 2
        segments.append({
            'd': f"M {p['x']} {p['y']} C {p['x']} {my}, {q['x']} {my}, {q['x']} {q['y']}",
            'lit': nodes[i]['status'] == 'done',
        })

    done = sum(1 for n in nodes if n['status'] == 'done')
    ctx = {
        'lesson': {'title': d['title'], 'subject': d['subject'], 'color': d['color'], 'guide': d['guide']},
        'nodes': nodes,
        'segments': segments,
        'canvas_h': len(nodes) * _PCRS_ROW_H + 60,
        'col_w': _PCRS_COL_W,
        'node_size': _PCRS_NODE,
        'progress_ratio': round(done / len(nodes), 4) if nodes else 0,
    }
    return render(request, 'student_learning/parcours_v2.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, écran LIRE / Lecteur (Phase C).
# DÉMO : reading en dur (mock READING.bio du design). Branchement reading_data après.
# ═══════════════════════════════════════════════════════════════════════════════
import re as _re
from html import escape as _esc

_READING_DEMO = {
    'lesson': {'title': "Biologie · La Cellule", 'subject': "SVT — Terminale", 'color': "#10B981"},
    'title': "La membrane plasmique", 'date': "Lundi 5 mai 2025",
    'terms': {
        "membrane plasmique": "La fine enveloppe qui entoure la cellule et contrôle ce qui entre et sort.",
        "bicouche lipidique": "Une double couche de molécules de gras qui forme la membrane.",
        "protéine de transport": "Une protéine insérée dans la membrane qui fait passer certaines molécules.",
        "osmose": "Le déplacement de l'eau à travers la membrane, selon les concentrations.",
        "transport actif": "Le passage d'une molécule à travers la membrane qui consomme de l'énergie (ATP).",
    },
    'sections': [
        {'id': "s1", 'title': "La frontière de la cellule", 'blocks': [
            {'type': "p", 'text': "Chaque cellule est entourée d'une membrane plasmique. C'est une frontière vivante : elle sépare l'intérieur de la cellule du monde extérieur, mais ce n'est pas un simple mur."},
            {'type': "def", 'term': "membrane plasmique", 'text': "la fine enveloppe qui entoure la cellule et contrôle ce qui entre et sort."},
            {'type': "callout", 'icon': "spark", 'label': "Le saviez-vous", 'text': "La membrane est si fine qu'il en faudrait des milliers empilées pour atteindre l'épaisseur d'une feuille de papier."},
            {'type': "check", 'variant': "tf", 'q': "La membrane laisse passer absolument tout, sans distinction.", 'answer': False, 'explain': "Elle est sélective : elle choisit ce qui passe."},
        ]},
        {'id': "s2", 'title': "De quoi est-elle faite ?", 'blocks': [
            {'type': "p", 'text': "La membrane est formée d'une bicouche lipidique : deux couches de molécules de gras placées dos à dos. Des protéines y sont insérées pour gérer les passages."},
            {'type': "key", 'items': ["La membrane est une bicouche lipidique.", "Une protéine de transport fait passer les grosses molécules.", "L'eau, elle, passe presque librement."]},
            {'type': "example", 'text': "Le glucose, trop gros pour traverser seul, utilise une protéine de transport comme une porte sur mesure."},
            {'type': "reflect", 'id': "br1", 'prompt': "À ton avis, pourquoi la cellule a-t-elle besoin d'une barrière sélective plutôt qu'un mur fermé ? Note ton idée."},
        ]},
        {'id': "s3", 'title': "Comment les choses entrent ?", 'blocks': [
            {'type': "p", 'text': "L'eau traverse la membrane librement par osmose. D'autres molécules, elles, ont besoin d'énergie : c'est le transport actif, qui consomme de l'ATP, la « monnaie » énergétique de la cellule."},
            {'type': "def", 'term': "transport actif", 'text': "le passage d'une molécule à travers la membrane qui consomme de l'énergie (ATP)."},
            {'type': "warn", 'text': "Ne confonds pas osmose (passage de l'eau, sans énergie) et transport actif (passage avec énergie)."},
            {'type': "check", 'variant': "qcm", 'q': "Qu'est-ce qui fait passer le glucose à travers la membrane ?", 'options': ["La bicouche toute seule", "Une protéine de transport", "Rien, il passe partout"], 'answer': 1, 'explain': "Le glucose est trop gros : il passe par une protéine de transport."},
        ]},
        {'id': "s4", 'title': "L'essentiel à retenir", 'blocks': [
            {'type': "key", 'items': ["La membrane entoure et protège la cellule.", "Elle est sélective : une bicouche + des protéines.", "L'eau passe par osmose, certaines molécules par transport actif."]},
        ]},
    ],
}


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


def lecteur_v2_demo(request):
    """Écran LIRE v2 (DÉMO, reading en dur). Ungated. Branchement reading_data ensuite."""
    d = _READING_DEMO
    term_keys = list(d['terms'].keys())
    # Pré-calcul : rich_html pour les paragraphes ; tts par section.
    sections = []
    tts = []
    for si, s in enumerate(d['sections']):
        blocks = []
        sec_tts = []
        for bi, b in enumerate(s['blocks']):
            nb = dict(b, si=si, bi=bi)
            if b['type'] == 'p':
                nb['rich_html'] = _reader_rich(b['text'], term_keys)
            blocks.append(nb)
            t = _reader_txt_of(b)
            if t:
                sec_tts.append({'bi': bi, 'text': t})
        sections.append({'id': s['id'], 'title': s['title'], 'blocks': blocks})
        tts.append(sec_tts)

    ctx = {
        'lesson': d['lesson'],
        'subject_short': d['lesson']['subject'].split('—')[0].strip(),
        'reading_title': d['title'],
        'sections': sections,
        'section_titles': [s['title'] for s in d['sections']],
        'terms': d['terms'],
        'tts': tts,
        'n_sections': len(sections),
    }
    return render(request, 'student_learning/lecteur_v2.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, QUIZ math_expression (Phase C, DÉMO).
# MathQuill (saisie maths visuelle) + pont LaTeX→format serveur (norm ^/espaces/casse).
# Données en dur. Les `equivalents` incluent la forme CANONIQUE produite par le
# convertisseur (frac→(a)/(b), sqrt(), ^) — au branchement réel, B1 devra émettre
# ces équivalents canoniques (ou on ajoutera sympy côté serveur).
# ═══════════════════════════════════════════════════════════════════════════════

_QUIZ_MATH_DEMO = {
    'lesson': {'title': "Maths · Calcul littéral", 'subject': "Mathématiques — 3ème", 'color': "#22D3EE"},
    'questions': [
        {
            'instruction': "Développe (x + 1)².",
            'correct': "x^2+2x+1",
            'equivalents': ["x^2 + 2*x + 1", "1+2x+x^2", "1 + 2*x + x^2"],
            'explanation': "(x + 1)² = x² + 2x + 1.",
        },
        {
            'instruction': "Simplifie la fraction 6/9.",
            'correct': "2/3",
            'equivalents': ["(2)/(3)"],   # forme produite par le convertisseur \frac{2}{3}
            'explanation': "6/9 = 2/3 (on divise haut et bas par 3).",
        },
        {
            'instruction': "Écris « la racine carrée de x ».",
            'correct': "sqrt(x)",
            'equivalents': [],            # le convertisseur \sqrt{x} → sqrt(x)
            'explanation': "√x s'écrit sqrt(x).",
        },
    ],
}


def quiz_math_v2_demo(request):
    """Quiz math_expression v2 (DÉMO, MathQuill). Ungated. Branchement réel ensuite."""
    d = _QUIZ_MATH_DEMO
    return render(request, 'student_learning/quiz_math_v2.html', {
        'lesson': d['lesson'],
        'questions': d['questions'],
        'n_questions': len(d['questions']),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, QUIZ famille CHOISIR (Phase C, DÉMO).
# 6 types : mcq_single, mcq_multiple, true_false, k_prime, odd_one_out,
# spot_the_bug. Un bloc Alpine autonome par type ; shell coordinateur commun.
# Éval client-side miroir exact de evaluate_answer_v2. Données en dur.
# Route v2 séparée /learn/v2/quiz-choisir/ ; v1 + autres écrans v2 intacts.
# ═══════════════════════════════════════════════════════════════════════════════

_QUIZ_CHOISIR_DEMO = {
    'lesson': {'title': "Révisions · Mix de matières", 'subject': "Divers — démo", 'color': "#22D3EE"},
    'questions': [
        {
            'type': 'mcq_single',
            'instruction': "Qui a fondé l'Empire du Mali au XIIIe siècle ?",
            'options': ["Soundiata Keïta", "Mansa Moussa", "Samory Touré", "Askia Mohamed"],
            'answer_index': 0,
            'explanation': "Soundiata Keïta a fondé l'Empire du Mali après la bataille de Kirina en 1235.",
        },
        {
            'type': 'mcq_multiple',
            'instruction': "Lesquels de ces éléments sont des organites de la cellule eucaryote ?",
            'options': ["Mitochondrie", "Ribosome", "Chloroplaste", "Noyau", "ATP"],
            'answer_indices': [0, 1, 2, 3],
            'explanation': "L'ATP est une molécule énergétique, pas un organite. Les 4 autres sont bien des organites.",
        },
        {
            'type': 'true_false',
            'instruction': "L'Océan Pacifique est plus grand que l'Océan Atlantique.",
            'answer': True,
            'explanation': "Le Pacifique couvre ~165 M km², l'Atlantique ~106 M km². Le Pacifique est le plus grand.",
        },
        {
            'type': 'k_prime',
            'instruction': "Pour chaque affirmation sur l'électricité, indique Vrai ou Faux.",
            'statements': [
                {'text': "Le courant électrique est un déplacement de charges.", 'answer': True},
                {'text': "La tension s'exprime en Ampères.", 'answer': False},
                {'text': "Un conducteur laisse passer le courant.", 'answer': True},
                {'text': "Une pile produit un courant alternatif.", 'answer': False},
            ],
            'explanation': "La tension (V) et l'intensité (A) sont distinctes. Une pile produit du courant continu.",
        },
        {
            'type': 'odd_one_out',
            'instruction': "Quel mot est l'intrus parmi ces figures de style ?",
            'items': ["Métaphore", "Allitération", "Oxymore", "Synapse", "Anaphore"],
            'odd_index': 3,
            'explanation': "\"Synapse\" est un terme de neurologie (jonction entre neurones), pas une figure de style.",
        },
        {
            'type': 'spot_the_bug',
            'instruction': "Quelle ligne contient le bug ? La fonction doit calculer la moyenne.",
            'language': 'python',
            'code': [
                "def moyenne(notes):",
                "    total = 0",
                "    for note in notes:",
                "        total = note",
                "    return total / len(notes)",
            ],
            'buggy_line': 3,
            'correct_fix': "total += note",
            'explanation': "La ligne 4 écrase total à chaque tour au lieu d'accumuler. Il faut écrire total += note.",
        },
    ],
}


def quiz_choisir_v2_demo(request):
    """Quiz famille CHOISIR v2 (DÉMO, 6 types). Ungated. Branchement réel ensuite."""
    d = _QUIZ_CHOISIR_DEMO
    return render(request, 'student_learning/quiz_choisir_v2.html', {
        'lesson': d['lesson'],
        'questions': d['questions'],
        'n_questions': len(d['questions']),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, QUIZ famille NOMBRE (Phase C, DÉMO).
# 2 types : number_input + dynamic_formula.
# Éval client-side miroir de evaluate_answer_v2 (services.py:1661-1666).
# Pour dynamic_formula : le tirage est SIMULÉ côté client (démo uniquement).
# ⚠  En production, draw_dynamic_formula() est appelé SERVER-SIDE ; les variables
#    et la réponse attendue ne transitent JAMAIS par le client (anti-triche).
# Route v2 séparée /learn/v2/quiz-nombre/ ; v1 + autres écrans v2 intacts.
# ═══════════════════════════════════════════════════════════════════════════════

_QUIZ_NOMBRE_DEMO = {
    'lesson': {'title': "Maths & Sciences · Nombres", 'subject': "Mixte — démo", 'color': "#A78BFA"},
    'questions': [
        # 1. number_input — réponse entière exacte (géographie)
        {
            'type': 'number_input',
            'instruction': "Combien de régions administratives le Mali compte-t-il depuis la réforme de 2023 ?",
            'answer': 19,
            'tolerance': 0,
            'unit': 'régions',
            'explanation': "Le Mali est divisé en 19 régions depuis la réforme administrative de 2023.",
        },
        # 2. number_input — réponse décimale avec tolérance (maths)
        {
            'type': 'number_input',
            'instruction': "Quelle est la valeur de π (pi), arrondie à 2 décimales ?",
            'answer': 3.14,
            'tolerance': 0.005,
            'unit': '',
            'explanation': "π ≈ 3.14159… — 3.14 et 3.142 sont tous les deux acceptés (tolérance ±0.005).",
        },
        # 3. dynamic_formula — aire rectangle (résultat entier, tolérance 0)
        {
            'type': 'dynamic_formula',
            'instruction': "Calcule l'aire d'un rectangle de {l} m de long et {w} m de large.",
            'variables': {
                'l': {'min': 3, 'max': 12, 'step': 1},
                'w': {'min': 2, 'max': 9,  'step': 1},
            },
            'solution_formula': "l * w",
            'tolerance': 0,
            'unit': 'm²',
            'explanation': "Aire = longueur × largeur.",
        },
        # 4. dynamic_formula — distance (résultat entier, tolérance 0)
        {
            'type': 'dynamic_formula',
            'instruction': "Un train roule à {v} km/h pendant {t} h. Quelle distance parcourt-il ?",
            'variables': {
                'v': {'min': 60, 'max': 160, 'step': 10},
                't': {'min': 2,  'max': 5,   'step': 1},
            },
            'solution_formula': "v * t",
            'tolerance': 0,
            'unit': 'km',
            'explanation': "Distance = Vitesse × Temps.",
        },
    ],
}


def quiz_nombre_v2_demo(request):
    """Quiz famille NOMBRE v2 (DÉMO, 2 types). Ungated. Branchement réel ensuite."""
    d = _QUIZ_NOMBRE_DEMO
    return render(request, 'student_learning/quiz_nombre_v2.html', {
        'lesson': d['lesson'],
        'questions': d['questions'],
        'n_questions': len(d['questions']),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, QUIZ famille ORDONNER (Phase C, DÉMO).
# 2 types : chrono_order + parsons_puzzle.
# Éval miroir de evaluate_answer_v2 (services.py:1658 / _eval_parsons:1566).
# Route v2 séparée /learn/v2/quiz-ordonner/ ; v1 + autres écrans v2 intacts.
# ═══════════════════════════════════════════════════════════════════════════════

_QUIZ_ORDONNER_DEMO = {
    'lesson': {'title': "Histoire & Code · Ordonner", 'subject': "Mixte — démo", 'color': "#F59E0B"},
    'questions': [
        # 1. chrono_order — grandes inventions de la communication
        # items[0]="Imprimerie Gutenberg", [1]="Écriture cunéiforme",
        # [2]="Internet grand public",      [3]="Télégraphe électrique"
        # Ordre correct : écriture→imprimerie→télégraphe→internet = [1,0,3,2]
        {
            'type': 'chrono_order',
            'instruction': "Remets ces inventions dans l'ordre chronologique, de la plus ancienne à la plus récente.",
            'items': [
                "L'imprimerie de Gutenberg (XVe siècle)",
                "L'écriture cunéiforme (IVe millénaire av. J.-C.)",
                "L'internet grand public (années 1990)",
                "Le télégraphe électrique (XIXe siècle)",
            ],
            'correct_order': [1, 0, 3, 2],
            'explanation': "Écriture cunéiforme (~3300 av. J.-C.) → Imprimerie (~1450) → Télégraphe (~1837) → Internet (~1990).",
        },
        # 2. chrono_order — étapes de résolution d'une équation
        # items[0]="Diviser/2", [1]="Vérifier", [2]="Soustraire 6"
        # Ordre correct : soustraire→diviser→vérifier = [2,0,1]
        {
            'type': 'chrono_order',
            'instruction': "Remets les étapes de résolution de 2x + 6 = 14 dans l'ordre.",
            'items': [
                "Diviser les deux membres par 2 → x = 4",
                "Vérifier : 2 × 4 + 6 = 14 ✓",
                "Soustraire 6 des deux membres → 2x = 8",
            ],
            'correct_order': [2, 0, 1],
            'explanation': "1. Soustraire 6 → 2x = 8.  2. Diviser par 2 → x = 4.  3. Vérifier le résultat.",
        },
        # 3. parsons_puzzle — fonction max_value (Python)
        {
            'type': 'parsons_puzzle',
            'instruction': "Remets les lignes de cette fonction Python dans l'ordre et corrige l'indentation.",
            'language': 'python',
            'lines': [
                {'id': 'a', 'text': 'def max_value(a, b):',  'correct_indent': 0},
                {'id': 'b', 'text': 'if a > b:',             'correct_indent': 1},
                {'id': 'c', 'text': 'return a',              'correct_indent': 2},
                {'id': 'd', 'text': 'else:',                  'correct_indent': 1},
                {'id': 'e', 'text': 'return b',              'correct_indent': 2},
            ],
            'correct_sequence': ['a', 'b', 'c', 'd', 'e'],
            'explanation': "La fonction teste a > b dans le if ; sinon (else) elle retourne b. Les return sont indentés de 2 niveaux.",
        },
        # 4. parsons_puzzle — boucle for avec accumulateur (Python)
        {
            'type': 'parsons_puzzle',
            'instruction': "Remets ce programme Python dans l'ordre et corrige l'indentation. Il calcule la somme de 1 à 5.",
            'language': 'python',
            'lines': [
                {'id': 'a', 'text': 'total = 0',            'correct_indent': 0},
                {'id': 'b', 'text': 'for i in range(1, 6):', 'correct_indent': 0},
                {'id': 'c', 'text': 'total += i',           'correct_indent': 1},
                {'id': 'd', 'text': 'print(total)',         'correct_indent': 0},
            ],
            'correct_sequence': ['a', 'b', 'c', 'd'],
            'explanation': "On initialise total=0, on boucle de 1 à 5 en accumulant chaque i, puis on affiche 15.",
        },
    ],
}


def quiz_ordonner_v2_demo(request):
    """Quiz famille ORDONNER v2 (DÉMO, 2 types). Ungated. Branchement réel ensuite."""
    d = _QUIZ_ORDONNER_DEMO
    return render(request, 'student_learning/quiz_ordonner_v2.html', {
        'lesson': d['lesson'],
        'questions': d['questions'],
        'n_questions': len(d['questions']),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Portail élève, QUIZ famille ASSOCIER (Phase C, DÉMO).
# 1 type : matching (13e et dernier type du moteur).
# Éval miroir de _eval_matching (services.py:1559) :
#   student[i] = origIdx du right choisi pour left[i] ; correct ssi == [0..n-1].
# Le mélange de la colonne droite se fait CÔTÉ CLIENT (démo).
# Route v2 séparée /learn/v2/quiz-associer/ ; v1 + autres écrans v2 intacts.
# ═══════════════════════════════════════════════════════════════════════════════

_QUIZ_ASSOCIER_DEMO = {
    'lesson': {'title': "Sciences & Géo · Associer", 'subject': "Mixte — démo", 'color': "#22D3EE"},
    'questions': [
        # 1. matching — organes et fonctions
        {
            'type': 'matching',
            'instruction': "Associe chaque organe à sa fonction principale.",
            'pairs': [
                {'left': 'Cœur',    'right': 'Pompe le sang'},
                {'left': 'Poumon',  'right': 'Échange l\'oxygène'},
                {'left': 'Cerveau', 'right': 'Coordonne le corps'},
                {'left': 'Rein',    'right': 'Filtre le sang'},
            ],
            'explanation': "Cœur → pompe le sang. Poumon → échange O₂/CO₂. Cerveau → coordonne. Rein → filtre.",
        },
        # 2. matching — pays d'Afrique de l'Ouest et capitales
        {
            'type': 'matching',
            'instruction': "Associe chaque pays à sa capitale.",
            'pairs': [
                {'left': 'Mali',         'right': 'Bamako'},
                {'left': 'Sénégal',      'right': 'Dakar'},
                {'left': 'Côte d\'Ivoire','right': 'Yamoussoukro'},
                {'left': 'Niger',        'right': 'Niamey'},
                {'left': 'Burkina Faso', 'right': 'Ouagadougou'},
            ],
            'explanation': "Mali→Bamako, Sénégal→Dakar, C. d'Ivoire→Yamoussoukro, Niger→Niamey, Burkina→Ouagadougou.",
        },
        # 3. matching — opérateurs Python
        {
            'type': 'matching',
            'instruction': "Associe chaque opérateur Python à son rôle.",
            'pairs': [
                {'left': '%',  'right': 'Reste de division'},
                {'left': '**', 'right': 'Puissance'},
                {'left': '//', 'right': 'Division entière'},
                {'left': '!=', 'right': 'Différent de'},
            ],
            'explanation': "% = modulo, ** = puissance, // = division entière, != = différent de.",
        },
    ],
}


def quiz_associer_v2_demo(request):
    """Quiz famille ASSOCIER v2 (DÉMO, matching). Ungated. Branchement réel ensuite."""
    d = _QUIZ_ASSOCIER_DEMO
    return render(request, 'student_learning/quiz_associer_v2.html', {
        'lesson': d['lesson'],
        'questions': d['questions'],
        'n_questions': len(d['questions']),
    })


# ─────────────────────────────────────────────────────────────────
# STORY IMMERSIVE v2 — démo cinématographique
# ─────────────────────────────────────────────────────────────────
_STORY_DEMO = {
    'lesson': {
        'title': 'Biologie · La Cellule',
        'subject': 'SVT — Terminale',
        'color': '#10B981',
    },
    'scene': {'name': 'À l\'intérieur de la cellule', 'c1': '#10B981', 'c2': '#0EA5E9'},
    'characters': [
        {'id': 'cyto', 'name': 'Cyto', 'role': 'Guide cellulaire', 'color': '#10B981'},
        {'id': 'nano', 'name': 'Nano', 'role': 'Molécule de glucose', 'color': '#F59E0B'},
    ],
    'steps': [
        {'type': 'narration', 'text': 'Marché cellulaire, à midi. Une petite molécule de sucre cherche à entrer…'},
        {'type': 'npc', 'who': 'cyto', 'text': 'Salut ! Je suis Cyto, ton guide. Voici Nano, une molécule de glucose qui veut entrer dans la cellule.'},
        {'type': 'npc', 'who': 'nano', 'text': 'La porte est immense et je suis tout petit… comment je passe ?'},
        {'type': 'choice', 'prompt': 'Aide Nano : par où franchir la membrane ?', 'options': [
            {'label': 'Par une protéine de transport', 'correct': True, 'reply': 'Exact ! On passe par une protéine, jamais en force.'},
            {'label': 'À travers la bicouche, en force', 'reply': 'Impossible : la membrane bloque les grosses molécules.'},
        ]},
        {'type': 'npc', 'who': 'cyto', 'text': 'Mais cette entrée coûte de l\'énergie. Quelle molécule la fournit ?'},
        {'type': 'input', 'prompt': 'La molécule d\'énergie (3 lettres)', 'answers': ['atp'], 'hint': 'A_P, la « monnaie » de la cellule.', 'ok': 'ATP, parfait. Tu connais bien ta biochimie.'},
        {'type': 'npc', 'who': 'nano', 'text': 'Ça y est, je sens que je bouge ! Mais dans quel ordre ça se passe ?'},
        {'type': 'tokens', 'prompt': 'Remets le transport dans l\'ordre :', 'tokens': ['Le glucose entre dans la cellule', 'Le glucose se lie à la protéine', 'La protéine change de forme'], 'solution': ['Le glucose se lie à la protéine', 'La protéine change de forme', 'Le glucose entre dans la cellule'], 'ok': 'Transport actif maîtrisé !'},
        {'type': 'blank', 'prompt': 'Complète la phrase :', 'parts': ['Le transport actif nécessite de l\'énergie sous forme d\'', '.'], 'answer': 'ATP', 'options': ['ATP', 'ADP', 'ARN', 'ADN'], 'ok': 'Exactement — l\'ATP est la monnaie énergétique de la cellule.'},
        {'type': 'npc', 'who': 'cyto', 'text': 'Bravo. Tu as fait entrer Nano dans la cellule, étape par étape. Tu maîtrises le transport membranaire !'},
    ],
}


def story_v2_demo(request):
    """Story cinématographique immersive v2 (DÉMO). Ungated.
    finish_url vide → le player ne POSTe aucune complétion (mode démo)."""
    d = _STORY_DEMO
    return render(request, 'student_learning/story_v2.html', {
        'lesson':      d['lesson'],
        'scene':       d['scene'],
        'characters':  d['characters'],
        'steps':       d['steps'],
        'finish_url':  '',
        'parcours_url': reverse('learn:parcours-v2-demo'),
    })


# ─────────────────────────────────────────────────────────────────
# EXAM SOBRE v2 — démo 4 phases (intro / épreuve / confirmation / bilan)
# ─────────────────────────────────────────────────────────────────
_EXAM_DEMO = {
    'lesson': {
        'title': 'Biologie · La Cellule',
        'subject': 'SVT — Terminale',
    },
    'meta': {
        'title': 'Examen — Membrane & Transports',
        'duration_s': 600,
        'pass_mark': 0.6,
    },
    'questions': [
        {
            'type': 'choisir', 'id': 'q0',
            'concept_id': 'membrane', 'concept_name': 'Membrane & échanges',
            'prompt': 'Quelle structure cellulaire contrôle les échanges entre la cellule et son milieu ?',
            'options': ['La membrane plasmique', 'Le noyau', 'La mitochondrie', 'Le ribosome'],
            'correct_idx': 0,
            'explanation': 'La membrane plasmique est la frontière sélective de la cellule — elle choisit ce qui entre et sort.',
        },
        {
            'type': 'choisir', 'id': 'q1',
            'concept_id': 'membrane', 'concept_name': 'Membrane & échanges',
            'prompt': 'De quoi est principalement composée la membrane plasmique ?',
            'options': ['Protéines uniquement', 'Bicouche de phospholipides + protéines', 'Glucides + lipides', 'ADN + protéines'],
            'correct_idx': 1,
            'explanation': 'La membrane est une bicouche de phospholipides dans laquelle sont insérées des protéines membranaires.',
        },
        {
            'type': 'input', 'id': 'q2',
            'concept_id': 'transport', 'concept_name': 'Transport membranaire',
            'prompt': 'Quelle molécule énergétique est indispensable au transport actif ? (sigle, 3 lettres)',
            'answers': ['atp'],
            'explanation': "Le transport actif consomme de l'ATP, la monnaie énergétique universelle de la cellule.",
        },
        {
            'type': 'ordonner', 'id': 'q3',
            'concept_id': 'transport', 'concept_name': 'Transport membranaire',
            'prompt': 'Remets les étapes du transport actif dans l\'ordre chronologique :',
            'items': ['La protéine change de conformation', 'La molécule se lie à la protéine', "L'ATP est hydrolysé", 'La molécule est libérée dans la cellule'],
            'solution': ['La molécule se lie à la protéine', "L'ATP est hydrolysé", 'La protéine change de conformation', 'La molécule est libérée dans la cellule'],
            'explanation': "La liaison précède l'hydrolyse d'ATP, qui déclenche le changement de conformation, puis la libération.",
        },
        {
            'type': 'blank', 'id': 'q4',
            'concept_id': 'transport', 'concept_name': 'Transport membranaire',
            'prompt': 'Complète la phrase :',
            'parts': ["Le passage spontané de l'eau à travers la membrane selon le gradient de concentration s'appelle l'", '.'],
            'answer': 'osmose',
            'options': ['osmose', 'exocytose', 'électrolyse', 'diffusion'],
            'explanation': "L'osmose est le passage de l'eau à travers une membrane semi-perméable, sans consommation d'énergie.",
        },
        {
            'type': 'choisir', 'id': 'q5',
            'concept_id': 'energie', 'concept_name': 'Énergie cellulaire',
            'prompt': "Quel organite est le principal producteur d'ATP dans la cellule ?",
            'options': ['Le noyau', 'Le ribosome', 'La mitochondrie', "L'appareil de Golgi"],
            'correct_idx': 2,
            'explanation': "La mitochondrie est le siège de la respiration cellulaire et produit la grande majorité de l'ATP.",
        },
        {
            'type': 'associer', 'id': 'q6',
            'concept_id': 'energie', 'concept_name': 'Énergie cellulaire',
            'prompt': 'Associe chaque type de transport à sa caractéristique :',
            'left': ['Osmose', 'Transport actif', 'Diffusion facilitée'],
            'right': ["Eau, sans énergie", "Consomme de l'ATP", 'Protéine, sans énergie'],
            'pairs': {'0': 0, '1': 1, '2': 2},
            'explanation': "L'osmose déplace l'eau sans énergie ; le transport actif consomme de l'ATP ; la diffusion facilitée utilise une protéine mais pas d'énergie.",
        },
    ],
}


def exam_v2_demo(request):
    """Examen sobre v2 — 4 phases (DÉMO). Ungated."""
    d = _EXAM_DEMO
    return render(request, 'student_learning/exam_v2.html', {
        'lesson':    d['lesson'],
        'meta':      d['meta'],
        'questions': d['questions'],
    })


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

    cv = lesson.active_content_version
    if not cv:
        cv = (LessonContentVersion.objects
              .filter(lesson=lesson).order_by('-version').first())
    if not cv:
        from django.http import Http404
        raise Http404('Aucun contenu disponible.')

    nodes = assemble_nodes(cv, student)
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

    # Switcher 'Mes leçons' : toutes les leçons v2 de l'élève (marque la courante).
    my_lessons = _student_v2_lessons(student)
    for ml in my_lessons:
        ml['current'] = (ml['id'] == lesson.id)

    return render(request, 'student_learning/parcours_v2.html', {
        'lesson': {
            'title':  lesson.title,
            'subject': lesson.subject or '',
            'color':  cv.color or '#818CF8',
            'guide':  cv.guide or '',
        },
        'nodes':          nodes,
        'segments':       segments,
        'canvas_h':       len(nodes) * _PCRS_ROW_H + 60,
        'col_w':          _PCRS_COL_W,
        'node_size':      _PCRS_NODE,
        'progress_ratio': progress_ratio,
        'my_lessons':     my_lessons,
        'lecteur_url':    reverse('learn:lecteur-v2', kwargs={'lesson_id': lesson.id}),
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
    return render(request, 'student_learning/lecteur_v2.html', {
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
    return render(request, 'student_learning/story_v2.html', {
        'lesson': {'title': lesson.title, 'subject': lesson.subject or '',
                   'color': cv.color or '#10B981'},
        'scene':        sd.get('scene') or {},
        'characters':   sd.get('characters') or [],
        'steps':        sd.get('steps') or [],
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

    return render(request, 'student_learning/exam_runner_v2.html', {
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
# ADDITIF : les démos /v2/quiz-* (éval client) restent intactes.
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

    return render(request, 'student_learning/quiz_runner_v2.html', {
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
