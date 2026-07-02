import json
import logging
import os
import tempfile

from django.urls import reverse
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.mixins import teacher_required, get_school
from apps.lessons.models import Lesson, LessonStatus, LessonDeployment, Unit
from apps.lessons.services import (
    validate_lesson_file,
    call_architect, extract_content_from_file, _create_unit_skeleton,
    launch_unit_generation, is_generation_active,
)
from apps.lessons import versioning, quality
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


# (v1 retiré : _generate_async, lesson_list, lesson_upload, lesson_detail)


# ─── Déploiement toggle par classe (PARTAGÉ v1/v2 — utilisé par le déploiement v2) ─

def _is_validated(lesson):
    """La leçon est validée si sa version live porte le tampon de validation."""
    cv = lesson.active_content_version
    return bool(cv and cv.validated_at)


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

    # Gate : on ne publie pas une leçon non validée (une non validée n'a de toute
    # façon aucun déploiement actif → tout toggle = tentative d'activation).
    if not _is_validated(lesson):
        existing = LessonDeployment.objects.filter(
            lesson=lesson, school_class=school_class).first()
        resp = render(request, 'lessons/partials/deploy_card.html', {
            'lesson': lesson, 'class': school_class,
            'is_deployed': bool(existing and existing.is_active),
            'student_count': 0,
        })
        resp['HX-Trigger'] = json.dumps({'showToast': {
            'message': "Valide d'abord la leçon avant de la publier.", 'type': 'error'}})
        return resp

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


# (v1 retiré : lesson_preview, lesson_status, lesson_retry)


# ═══════════════════════════════════════════════════════════════════════════════
# VUES v2 (PORTAL_V2_SPEC) — upload d'unité.
# Architecte + skeleton SYNCHRONES (structure visible vite) ; génération longue en
# FOND (thread daemon + verrou, cf. services). Confirmer-lite : l'upload crée le
# skeleton en DRAFT, la génération attend le bouton « Lancer ».
# ═══════════════════════════════════════════════════════════════════════════════

def _unit_status_context(unit) -> dict:
    """Contexte partagé par unit_detail et unit_status (checklist des shells)."""
    lessons = list(unit.lessons.all().order_by('order', 'id'))
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
        # Validation prof : édition possible seulement en DRAFT (avant génération).
        'is_draft':          unit.status == LessonStatus.DRAFT,
        'can_delete':        total > 1,
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


def _teacher_classes(teacher, school):
    """Classes où l'enseignant intervient (pour le déploiement v2), avec compte élèves."""
    return list(
        SchoolClass.objects
        .filter(class_subjects__teacher=teacher, school=school, is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .distinct()
        .order_by('level', 'name')
    )


@teacher_required
def unit_list(request):
    """Liste des Unités v2 de l'enseignant (les leçons v2 vivent sous leur Unité)."""
    school = get_school(request)
    units = (Unit.objects.filter(teacher=request.user, school=school)
             .order_by('-created_at').prefetch_related('lessons'))
    units_data = []
    for u in units:
        lessons = list(u.lessons.all())
        ready = sum(1 for l in lessons if l.status == LessonStatus.READY)
        units_data.append({'unit': u, 'total': len(lessons), 'ready': ready})
    return render(request, 'lessons/unit_list.html', {'units_data': units_data})


@teacher_required
def unit_detail(request, unit_id):
    school = get_school(request)
    unit = get_object_or_404(Unit, pk=unit_id, teacher=request.user, school=school)
    ctx = _unit_status_context(unit)

    # Déploiement v2 (additif) : pour chaque leçon READY, les classes du prof + état
    # déployé. Réutilise deploy_card.html + lesson_deploy_toggle (mécanisme existant).
    ready_lessons = [l for l in ctx['lessons'] if l.status == LessonStatus.READY]
    classes = _teacher_classes(request.user, school) if ready_lessons else []
    deployed = set(
        LessonDeployment.objects
        .filter(lesson__in=ready_lessons, is_active=True)
        .values_list('lesson_id', 'school_class_id')
    )
    ctx['deploy_lessons'] = [{
        'lesson': l,
        'validated': _is_validated(l),
        'classes': [{'obj': c, 'is_deployed': (l.id, c.id) in deployed,
                     'student_count': c.student_count} for c in classes],
    } for l in ready_lessons]
    return render(request, 'lessons/unit_detail.html', ctx)


@teacher_required
@require_POST
def unit_generate(request, unit_id):
    """Lancer (1ère fois) OU Reprendre (après partiel/bloqué) la génération en fond."""
    school = get_school(request)
    unit = get_object_or_404(Unit, pk=unit_id, teacher=request.user, school=school)

    # Garde : pas de génération sur une unité vide (toutes les leçons supprimées).
    if unit.lessons.count() == 0:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Ajoute au moins une leçon avant de générer.', 'type': 'warning'}})
        return resp

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


# ─── Validation prof : édition du découpage (DRAFT only, HTMX) ─────────────────
# Renommer / réordonner / fusionner / supprimer les leçons AVANT génération.
# Toutes scopées unit.status == DRAFT ; retour = partial de la liste éditable.

def _unit_draft(request, unit_id):
    """Charge l'Unit du prof ; (unit, None) si DRAFT, (unit, erreur) sinon."""
    school = get_school(request)
    unit = get_object_or_404(Unit, pk=unit_id, teacher=request.user, school=school)
    if unit.status != LessonStatus.DRAFT:
        return unit, HttpResponse('Édition impossible : la génération est déjà lancée.', status=403)
    return unit, None


def _reindex_lessons(unit):
    """Renumérote order = 0,1,2… selon l'ordre courant (pas de trous)."""
    for i, l in enumerate(unit.lessons.all().order_by('order', 'id')):
        if l.order != i:
            l.order = i
            l.save(update_fields=['order'])


def _unit_edit_partial(request, unit):
    """Re-rend la liste éditable des leçons (cible HTMX, réaction instantanée)."""
    lessons = list(unit.lessons.all().order_by('order', 'id'))
    return render(request, 'lessons/partials/unit_lessons_edit.html', {
        'unit': unit,
        'lessons': lessons,
        'can_delete': len(lessons) > 1,
    })


@teacher_required
@require_POST
def unit_lesson_rename(request, unit_id, lesson_id):
    unit, err = _unit_draft(request, unit_id)
    if err:
        return err
    lesson = get_object_or_404(Lesson, pk=lesson_id, unit=unit)
    title = (request.POST.get('title') or '').strip()
    if not title:
        return HttpResponse('Titre requis.', status=422)
    lesson.title = title[:200]
    lesson.save(update_fields=['title'])
    return _unit_edit_partial(request, unit)


@teacher_required
@require_POST
def unit_lesson_delete(request, unit_id, lesson_id):
    unit, err = _unit_draft(request, unit_id)
    if err:
        return err
    if unit.lessons.count() <= 1:
        return HttpResponse('Au moins une leçon est requise.', status=422)
    get_object_or_404(Lesson, pk=lesson_id, unit=unit).delete()
    _reindex_lessons(unit)
    return _unit_edit_partial(request, unit)


@teacher_required
@require_POST
def unit_lesson_move(request, unit_id, lesson_id):
    unit, err = _unit_draft(request, unit_id)
    if err:
        return err
    direction = request.POST.get('direction')
    lessons = list(unit.lessons.all().order_by('order', 'id'))
    idx = next((i for i, l in enumerate(lessons) if l.id == int(lesson_id)), None)
    if idx is None:
        return _unit_edit_partial(request, unit)
    swap = idx - 1 if direction == 'up' else idx + 1 if direction == 'down' else None
    if swap is None or swap < 0 or swap >= len(lessons):
        return _unit_edit_partial(request, unit)   # extrémité → no-op
    a, b = lessons[idx], lessons[swap]
    a.order, b.order = b.order, a.order
    a.save(update_fields=['order'])
    b.save(update_fields=['order'])
    _reindex_lessons(unit)
    return _unit_edit_partial(request, unit)


@teacher_required
@require_POST
def unit_lesson_merge(request, unit_id, lesson_id):
    """Fusionne CETTE leçon avec la PRÉCÉDENTE (titre = celui de la précédente ;
    résumés concaténés), puis supprime celle-ci."""
    unit, err = _unit_draft(request, unit_id)
    if err:
        return err
    lessons = list(unit.lessons.all().order_by('order', 'id'))
    idx = next((i for i, l in enumerate(lessons) if l.id == int(lesson_id)), None)
    if idx is None or idx == 0:
        return HttpResponse('Fusion impossible : aucune leçon au-dessus.', status=422)
    cur, prev = lessons[idx], lessons[idx - 1]
    parts = [p for p in [(prev.summary or '').strip(), (cur.summary or '').strip()] if p]
    prev.summary = '\n\n'.join(parts)
    prev.save(update_fields=['summary'])
    cur.delete()
    _reindex_lessons(unit)
    return _unit_edit_partial(request, unit)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6 — Révision / Validation
# Le prof relit à plat (corrigés visibles), résout les drapeaux (structurel + IA),
# puis valide EN UNE FOIS. Aucun mode élève obligatoire. Valider = publish_draft.
# ═══════════════════════════════════════════════════════════════════════════════

def _index_flags(flags):
    idx = {}
    for f in flags:
        idx.setdefault((f['block'], f['item_id']), []).append(f)
    return idx


def _correct_indices(q):
    """Index(s) de la bonne réponse : answer_index (mcq_single) ou answer_indices."""
    single = q.get('answer_index')
    if isinstance(single, int) and not isinstance(single, bool):
        return [single]
    multi = q.get('answer_indices')
    return multi if isinstance(multi, list) else []


def _quiz_view(q, block, idx):
    return {'quiz': q, 'flags': idx.get((block, q.get('id')), []),
            'correct': _correct_indices(q)}


def _review_context(lesson, draft, flags):
    content = quality.content_of(draft)
    idx = _index_flags(flags)

    concepts = []
    for c in (content['concepts'] or []):
        if not isinstance(c, dict):
            continue
        quizzes = [_quiz_view(q, 'concepts', idx)
                   for q in (c.get('quiz') or []) if isinstance(q, dict)]
        concepts.append({'concept': c, 'quizzes': quizzes,
                         'has_flags': any(x['flags'] for x in quizzes)})

    exam = content['exam'] or {}
    exam_questions = [_quiz_view(q, 'exam', idx)
                      for q in (exam.get('questions') or []) if isinstance(q, dict)]

    return {
        'lesson':         lesson,
        'unit':           lesson.unit,
        'concepts':       concepts,
        'exam':           exam,
        'exam_questions': exam_questions,
        'exam_flags':     idx.get(('exam', 'exam'), []),
        'has_reading':    bool(content.get('reading')),
        'has_story':      bool(content.get('story')),
        'flag_count':     len(flags),
        'error_count':    sum(1 for f in flags if f['severity'] == 'error'),
        'warn_count':     sum(1 for f in flags if f['severity'] == 'warn'),
        'validated':      _is_validated(lesson),
        'ai_pending':     draft.ai_flags is None,
    }


def _get_teacher_lesson(request, lesson_id):
    return get_object_or_404(
        Lesson, pk=lesson_id, teacher=request.user, school=get_school(request))


def _render_review_body(request, lesson):
    draft = versioning.open_draft(lesson)
    return render(request, 'lessons/partials/review_body.html',
                  _review_context(lesson, draft, quality.review_flags(lesson)))


@teacher_required
def lesson_review(request, lesson_id):
    """Page de révision (survol à plat, corrigés, drapeaux). Ouvre le brouillon."""
    lesson = _get_teacher_lesson(request, lesson_id)
    draft = versioning.open_draft(lesson)
    ctx = _review_context(lesson, draft, quality.review_flags(lesson))
    return render(request, 'lessons/review.html', ctx)


@teacher_required
def lesson_ai_flags(request, lesson_id):
    """HTMX (load) : lance la critique IA une fois (cachée) puis renvoie le corps à jour."""
    lesson = _get_teacher_lesson(request, lesson_id)
    quality.compute_ai_flags(lesson)
    return _render_review_body(request, lesson)


@teacher_required
@require_POST
def lesson_dismiss_flag(request, lesson_id):
    """« C'est correct » : retire un doute IA du cache."""
    lesson = _get_teacher_lesson(request, lesson_id)
    draft = versioning.open_draft(lesson)
    item_id, code = request.POST.get('item_id'), request.POST.get('code')
    draft.ai_flags = [f for f in (draft.ai_flags or [])
                      if not (f.get('item_id') == item_id and f.get('code') == code)]
    draft.save(update_fields=['ai_flags', 'updated_at'])
    return _render_review_body(request, lesson)


@teacher_required
@require_POST
def lesson_regen_block(request, lesson_id):
    """↻ Régénérer un bloc (noyau/lecture/histoire) dans le brouillon + invalider l'IA."""
    lesson = _get_teacher_lesson(request, lesson_id)
    block = request.POST.get('block')
    try:
        versioning.regenerate_block(lesson, block)
        msg, typ = 'Bloc régénéré ✓', 'success'
    except Exception as e:
        logger.warning('Régénération bloc %s échouée : %s', block, e)
        msg, typ = 'Régénération impossible, réessaie.', 'error'
    draft = versioning.open_draft(lesson)
    if typ == 'success':
        draft.ai_flags = None                 # contenu changé → recalcul IA
        draft.save(update_fields=['ai_flags', 'updated_at'])
    resp = _render_review_body(request, lesson)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': msg, 'type': typ}})
    return resp


@teacher_required
@require_POST
def lesson_validate(request, lesson_id):
    """Valider et publier EN UNE FOIS. Gate serveur : erreurs structurelles bloquantes."""
    lesson = _get_teacher_lesson(request, lesson_id)
    errors = quality.blocking_errors(lesson)
    if errors:
        resp = _render_review_body(request, lesson)
        resp['HX-Trigger'] = json.dumps({'showToast': {
            'message': f'{len(errors)} erreur(s) à corriger avant de valider.', 'type': 'error'}})
        return resp
    versioning.publish_draft(lesson, validated_by=request.user)
    if lesson.status != LessonStatus.READY:
        lesson.status = LessonStatus.READY
        lesson.save(update_fields=['status', 'updated_at'])
    resp = HttpResponse(status=204)
    resp['HX-Redirect'] = (reverse('lessons:unit-detail', args=[lesson.unit_id])
                           if lesson.unit_id else reverse('lessons:unit-list'))
    return resp
