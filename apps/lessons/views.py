import logging
import threading

from django.db import close_old_connections
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.mixins import teacher_required, get_school
from apps.lessons.models import Lesson, LessonStatus, LessonDeployment
from apps.lessons.services import generate_lesson_with_ai, validate_lesson_file
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
    lessons = (
        Lesson.objects
        .filter(teacher=request.user, school=school)
        .order_by('-created_at')
    )
    stats = {
        'total':      lessons.count(),
        'ready':      lessons.filter(status=LessonStatus.READY).count(),
        'processing': lessons.filter(status=LessonStatus.PROCESSING).count(),
        'error':      lessons.filter(status=LessonStatus.ERROR).count(),
    }
    return render(request, 'lessons/list.html', {
        'lessons': lessons, 'stats': stats, 'school': school,
    })


# ─── Upload d'une leçon ──────────────────────────────────────────────────────

@teacher_required
def lesson_upload(request):
    school = get_school(request)

    def _build_classes_data():
        class_subjects = (
            ClassSubject.objects
            .filter(teacher=request.user)
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
                'name': cs.subject.name,
                'type': stype,
                'icon': icon,
                'bg':   bg,
                'text': text,
            })
        return list(classes.values())

    if request.method == 'GET':
        return render(request, 'lessons/upload.html', {
            'school':       school,
            'classes_data': _build_classes_data(),
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
            'classes_data': _build_classes_data(),
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
    teacher_classes = (
        SchoolClass.objects
        .filter(class_subjects__teacher=request.user, school=school, is_active=True)
        .distinct()
        .order_by('level', 'name')
    )
    deployed_class_ids = set(
        LessonDeployment.objects
        .filter(lesson=lesson, is_active=True)
        .values_list('school_class_id', flat=True)
    )
    return render(request, 'lessons/detail.html', {
        'lesson': lesson,
        'teacher_classes': teacher_classes,
        'deployed_class_ids': deployed_class_ids,
        'school': school,
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
    resp['HX-Redirect'] = f'/teacher/lessons/{lesson.id}/'
    return resp
