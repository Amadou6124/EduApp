import json
import logging
import os
import tempfile
import threading
from types import SimpleNamespace

from django.db import close_old_connections
from django.urls import reverse
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.mixins import teacher_required, get_school
from apps.lessons.models import Lesson, LessonStatus, LessonDeployment, Unit
from apps.lessons.services import (
    generate_lesson_with_ai, validate_lesson_file,
    call_architect, extract_content_from_file, _create_unit_skeleton,
    launch_unit_generation, is_generation_active,
)
from apps.schools.models import SchoolClass, ClassSubject, EducationLevel

logger = logging.getLogger(__name__)

# ─── Heuristique matière → type ──────────────────────────────────────────────

SUBJECT_TYPE_HINTS = {
    'français': 'literary', 'littérature': 'literary', 'dictée': 'literary',
    'math': 'math', 'maths': 'math',
    'anglais': 'language', 'langue': 'language',
    'histoire': 'geography', 'géo': 'geography', 'ecm': 'geography',
    'biologie': 'scientific', 'svt': 'scientific', 'physique': 'scientific',
    'informatique': 'code', 'info': 'code',
    'comptabilité': 'accounting',
}

SUBJECT_META = {
    'literary':   ('book-open',   'bg-indigo-50',  'text-indigo-600'),
    'math':       ('hash',        'bg-blue-50',    'text-blue-600'),
    'language':   ('globe',       'bg-emerald-50', 'text-emerald-600'),
    'geography':  ('map-pin',     'bg-amber-50',   'text-amber-600'),
    'scientific': ('activity',    'bg-green-50',   'text-green-600'),
    'code':       ('code',        'bg-purple-50',  'text-purple-600'),
    'accounting': ('bar-chart-2', 'bg-orange-50',  'text-orange-600'),
    'other':      ('book',        'bg-gray-50',    'text-gray-500'),
}


def get_subject_type(name: str) -> str:
    n = name.lower()
    for key, val in SUBJECT_TYPE_HINTS.items():
        if key in n:
            return val
    return 'other'


def _build_classes_data(teacher):
    """Classes + matières assignées à l'enseignant, pour l'assistant d'upload (v1 ET v2).

    Chaque classe porte son niveau (level/level_label) ; chaque matière son type déduit
    (heuristique get_subject_type) + ses couleurs. Source de la « déduction » : le prof
    choisit une classe+matière, tout le reste (niveau, type) en découle."""
    class_subjects = (
        ClassSubject.objects
        .filter(teacher=teacher)
        .select_related('school_class', 'subject')
        .order_by('school_class__name', 'subject__name')
    )
    classes: dict = {}
    for cs in class_subjects:
        cls = cs.school_class
        if cls.id not in classes:
            classes[cls.id] = {
                'id':          cls.id,
                'name':        cls.name,
                'level':       cls.level,
                'level_label': cls.get_level_display(),
                'subjects':    [],
            }
        stype = get_subject_type(cs.subject.name)
        icon, bg, text = SUBJECT_META.get(stype, SUBJECT_META['other'])
        classes[cls.id]['subjects'].append({
            'name': cs.subject.name, 'type': stype,
            'icon': icon, 'bg': bg, 'text': text,
        })
    return list(classes.values())


def _generate_async(lesson_id):
    """Génération IA en thread d'arrière-plan (pas de Celery)."""
    close_old_connections()
    try:
        generate_lesson_with_ai(Lesson.objects.get(pk=lesson_id))
    except Exception as e:
        logger.error('Génération async échouée leçon %s: %s', lesson_id, e)
    finally:
        close_old_connections()


# ─── Liste des leçons du prof ────────────────────────────────────────────────

@teacher_required
def lesson_list(request):
    school = get_school(request)
    base_qs = Lesson.objects.filter(teacher=request.user, school=school)
    stats = {
        'total':      base_qs.count(),
        'ready':      base_qs.filter(status=LessonStatus.READY).count(),
        'processing': base_qs.filter(status=LessonStatus.PROCESSING).count(),
        'error':      base_qs.filter(status=LessonStatus.ERROR).count(),
    }
    lessons = (
        base_qs
        .annotate(deployed_count=Count('deployments', filter=Q(deployments__is_active=True)))
        .order_by('-created_at')
    )
    return render(request, 'lessons/list.html', {
        'lessons': lessons, 'stats': stats, 'school': school,
    })


# ─── Upload d'une leçon ──────────────────────────────────────────────────────

@teacher_required
def lesson_upload(request):
    school = get_school(request)

    if request.method == 'GET':
        return render(request, 'lessons/upload.html', {
            'school':       school,
            'classes_data': _build_classes_data(request.user),
        })

    # POST ──────────────────────────────────────────────────────────────────────
    errors = {}

    source_file = request.FILES.get('source_file')
    source_type = None
    if not source_file:
        errors['source_file'] = 'Fichier requis.'
    else:
        try:
            source_type = validate_lesson_file(source_file)
        except ValueError as e:
            errors['source_file'] = str(e)

    selected_class_id     = request.POST.get('selected_class_id', '').strip()
    selected_level        = request.POST.get('selected_level', '').strip()
    selected_level_detail = request.POST.get('selected_level_detail', '').strip()
    selected_subject_name = request.POST.get('selected_subject_name', '').strip()
    selected_subject_type = request.POST.get('selected_subject_type', 'other')
    title                 = request.POST.get('title', '').strip()

    if not selected_class_id:
        errors['class'] = 'Classe requise.'
    if not selected_subject_name:
        errors['subject'] = 'Matière requise.'

    if not title:
        title = f"Leçon — {selected_subject_name}" if selected_subject_name else "Nouvelle leçon"

    if errors:
        return render(request, 'lessons/upload.html', {
            'school':       school,
            'classes_data': _build_classes_data(request.user),
            'errors':       errors,
        }, status=422)

    lesson = Lesson.objects.create(
        teacher=request.user,
        school=school,
        title=title,
        subject=selected_subject_name,
        subject_type=selected_subject_type,
        level=selected_level,
        level_detail=selected_level_detail,
        source_file=source_file,
        source_type=source_type,
        status=LessonStatus.DRAFT,
    )

    threading.Thread(target=_generate_async, args=[lesson.id], daemon=True).start()
    return redirect('lessons:detail', lesson_id=lesson.id)


# ─── Détail d'une leçon ──────────────────────────────────────────────────────

@teacher_required
def lesson_detail(request, lesson_id):
    school = get_school(request)
    lesson = get_object_or_404(
        Lesson, pk=lesson_id, teacher=request.user, school=school,
    )
    deployed_class_ids = set(
        LessonDeployment.objects
        .filter(lesson=lesson, is_active=True)
        .values_list('school_class_id', flat=True)
    )
    teacher_classes = (
        SchoolClass.objects
        .filter(class_subjects__teacher=request.user, school=school, is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .distinct()
        .order_by('level', 'name')
    )
    teacher_classes_data = [
        {
            'obj':           c,
            'is_deployed':   c.id in deployed_class_ids,
            'student_count': c.student_count,
        }
        for c in teacher_classes
    ]
    deployed_count = sum(1 for item in teacher_classes_data if item['is_deployed'])
    return render(request, 'lessons/detail.html', {
        'lesson':               lesson,
        'teacher_classes_data': teacher_classes_data,
        'total_classes':        len(teacher_classes_data),
        'deployed_count':       deployed_count,
        'school':               school,
    })


# ─── Déploiement toggle par classe ───────────────────────────────────────────

@teacher_required
@require_POST
def lesson_deploy_toggle(request, lesson_id, class_id):
    """Active ou désactive un LessonDeployment pour une classe donnée."""
    school = get_school(request)
    lesson = get_object_or_404(
        Lesson, pk=lesson_id, teacher=request.user,
        school=school, status=LessonStatus.READY,
    )
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=school)

    deployment, created = LessonDeployment.objects.get_or_create(
        lesson=lesson,
        school_class=school_class,
        defaults={'school': school, 'deployed_by': request.user, 'is_active': True},
    )
    if not created:
        deployment.is_active = not deployment.is_active
        deployment.save(update_fields=['is_active'])

    is_active = deployment.is_active
    student_count = (
        SchoolClass.objects
        .filter(pk=class_id)
        .annotate(cnt=Count('students', filter=Q(students__is_active=True)))
        .values_list('cnt', flat=True)
        .first() or 0
    )
    toast_msg = (
        f'Leçon publiée en {school_class.name} ✓' if is_active
        else f'Retirée de {school_class.name}'
    )
    resp = render(request, 'lessons/partials/deploy_card.html', {
        'lesson':        lesson,
        'class':         school_class,
        'is_deployed':   is_active,
        'student_count': student_count,
    })
    resp['HX-Trigger'] = json.dumps({
        'showToast': {'message': toast_msg, 'type': 'success' if is_active else 'info'}
    })
    return resp


# ─── Prévisualisation enseignant ─────────────────────────────────────────────

@teacher_required
def lesson_preview(request, lesson_id):
    """Prévisualisation enseignant — même rendu que l'élève, sans tracking."""
    school = get_school(request)
    lesson = get_object_or_404(
        Lesson, pk=lesson_id, teacher=request.user,
        school=school, status=LessonStatus.READY,
    )
    blocks = (lesson.structured_content or {}).get('blocks', [])
    return render(request, 'learn/lesson.html', {
        'lesson':       lesson,
        'blocks':       blocks,
        'total_blocks': len(blocks),
        'initial_pct':  0,
        'progress':     SimpleNamespace(last_block_index=0, notes={}, is_completed=False),
        'has_story':    bool(lesson.story_data),
        'has_quiz':     lesson.quiz_count > 0,
        'already_done': False,
        'student':      None,
        'is_preview':   True,
    })


# ─── Statut (polling HTMX) ───────────────────────────────────────────────────

@teacher_required
def lesson_status(request, lesson_id):
    """Partial HTMX appelé par hx-trigger='every 2s' tant que status=processing."""
    school = get_school(request)
    lesson = get_object_or_404(
        Lesson, pk=lesson_id, teacher=request.user, school=school,
    )
    if request.headers.get('HX-Request'):
        # États terminaux → recharge la page pour afficher le détail complet.
        if lesson.status in (LessonStatus.READY, LessonStatus.ERROR):
            resp = HttpResponse(status=204)
            resp['HX-Refresh'] = 'true'
            return resp
        return render(request, 'lessons/partials/lesson_status_card.html', {'lesson': lesson})

    return JsonResponse({
        'status': lesson.status,
        'error': lesson.processing_error,
        'quiz_count': lesson.quiz_count,
        'flashcard_count': lesson.flashcard_count,
    })


# ─── Relancer la génération ──────────────────────────────────────────────────

@teacher_required
def lesson_retry(request, lesson_id):
    """Relance la génération si status=error. POST uniquement."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school = get_school(request)
    lesson = get_object_or_404(
        Lesson, pk=lesson_id, teacher=request.user, school=school,
        status=LessonStatus.ERROR,
    )

    threading.Thread(target=_generate_async, args=[lesson.id], daemon=True).start()

    resp = HttpResponse(status=200)
    resp['HX-Trigger'] = '{"showToast": {"message": "Génération relancée...", "type": "info"}}'
    resp['HX-Redirect'] = reverse('lessons:detail', args=[lesson.id])
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# VUES v2 (PORTAL_V2_SPEC) — upload d'unité (parallèle au v1, sans le toucher).
# Architecte + skeleton SYNCHRONES (structure visible vite) ; génération longue en
# FOND (thread daemon + verrou, cf. services). Confirmer-lite : l'upload crée le
# skeleton en DRAFT, la génération attend le bouton « Lancer ».
# ═══════════════════════════════════════════════════════════════════════════════

def _unit_status_context(unit) -> dict:
    """Contexte partagé par unit_detail et unit_status (checklist des shells)."""
    lessons = list(unit.lessons.all().order_by('id'))
    ready = sum(1 for l in lessons if l.status == LessonStatus.READY)
    total = len(lessons)
    return {
        'unit':              unit,
        'lessons':           lessons,
        'ready_count':       ready,
        'total_count':       total,
        'progress_pct':      int(ready / total * 100) if total else 0,
        'all_ready':         total > 0 and ready == total,
        'generation_active': is_generation_active(unit),
        'has_error':         any(l.status == LessonStatus.ERROR for l in lessons),
    }


@teacher_required
def unit_upload(request):
    """Upload v2 : extrait → Architecte (sync) → skeleton DRAFT → redirect détail.
    NE lance PAS la génération (confirmer-lite : bouton « Lancer » ensuite)."""
    school = get_school(request)
    if request.method == 'GET':
        return render(request, 'lessons/unit_upload.html', {
            'school': school,
            'classes_data': _build_classes_data(request.user),
        })

    # POST — les champs sont DÉDUITS par l'assistant (classe+matière choisies),
    # pas saisis : mêmes noms que le v1.
    errors = {}
    source_file = request.FILES.get('source_file')
    source_type = None
    if not source_file:
        errors['source_file'] = 'Fichier requis.'
    else:
        try:
            source_type = validate_lesson_file(source_file)
        except ValueError as e:
            errors['source_file'] = str(e)

    selected_class_id = request.POST.get('selected_class_id', '').strip()
    subject_name  = request.POST.get('selected_subject_name', '').strip()
    subject_type  = request.POST.get('selected_subject_type', 'other')
    level         = request.POST.get('selected_level', '').strip() or EducationLevel.FONDAMENTAL_1
    level_detail  = request.POST.get('selected_level_detail', '').strip()
    if not selected_class_id:
        errors['class'] = 'Classe requise.'
    if not subject_name:
        errors['subject'] = 'Matière requise.'

    if errors:
        return render(request, 'lessons/unit_upload.html',
                      {'school': school, 'classes_data': _build_classes_data(request.user),
                       'errors': errors}, status=422)

    # Extraction synchrone via fichier temporaire (extract attend un CHEMIN ; le
    # fichier uploadé est en mémoire). Le worker re-extraira depuis source_file.path.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            for chunk in source_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        content = extract_content_from_file(tmp_path, source_type)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
    source_file.seek(0)  # rembobiner pour la sauvegarde sur l'Unit

    # Temps 1 — Architecte (synchrone, ~10s)
    try:
        structure = call_architect(content)
    except Exception as e:
        logger.error('Architecte upload échoué: %s', e)
        return render(request, 'lessons/unit_upload.html',
                      {'school': school, 'classes_data': _build_classes_data(request.user),
                       'errors': {'architecte': "L'analyse du document a échoué. Réessayez."}},
                      status=502)

    if structure.get('error') == 'unreadable':
        return render(request, 'lessons/unit_upload.html',
                      {'school': school, 'classes_data': _build_classes_data(request.user),
                       'errors': {'architecte': structure.get('message', 'Document illisible.')}},
                      status=422)

    unit = _create_unit_skeleton(
        structure,
        teacher=request.user, school=school,
        subject=subject_name,          # matière du prof = vérité terrain (surcharge l'IA)
        subject_type=subject_type, level=level, level_detail=level_detail,
        source_file=source_file, source_type=source_type,
        initial_status=LessonStatus.DRAFT,
    )
    return redirect('lessons:unit-detail', unit_id=unit.id)


@teacher_required
def unit_detail(request, unit_id):
    school = get_school(request)
    unit = get_object_or_404(Unit, pk=unit_id, teacher=request.user, school=school)
    return render(request, 'lessons/unit_detail.html', _unit_status_context(unit))


@teacher_required
@require_POST
def unit_generate(request, unit_id):
    """Lancer (1ère fois) OU Reprendre (après partiel/bloqué) la génération en fond."""
    school = get_school(request)
    unit = get_object_or_404(Unit, pk=unit_id, teacher=request.user, school=school)

    launched = launch_unit_generation(unit)
    msg = 'Génération lancée…' if launched else 'Génération déjà en cours.'
    typ = 'info' if launched else 'warning'
    resp = HttpResponse(status=200)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': msg, 'type': typ}})
    resp['HX-Redirect'] = reverse('lessons:unit-detail', args=[unit.id])
    return resp


@teacher_required
def unit_status(request, unit_id):
    """Polling HTMX (every ~3s tant qu'une génération est active) : checklist des shells.
    Quand la génération est terminée (verrou libéré) → 204 + HX-Refresh."""
    school = get_school(request)
    unit = get_object_or_404(Unit, pk=unit_id, teacher=request.user, school=school)

    if request.headers.get('HX-Request'):
        if not is_generation_active(unit):
            resp = HttpResponse(status=204)
            resp['HX-Refresh'] = 'true'
            return resp
        return render(request, 'lessons/partials/unit_status.html', _unit_status_context(unit))

    ctx = _unit_status_context(unit)
    return JsonResponse({
        'status': unit.status,
        'ready': ctx['ready_count'],
        'total': ctx['total_count'],
        'generation_active': ctx['generation_active'],
    })
