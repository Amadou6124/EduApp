import logging
import threading

from django.db import close_old_connections
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.mixins import teacher_required, get_school
from apps.lessons.models import Lesson, LessonStatus, LessonDeployment, SubjectType
from apps.lessons.services import generate_lesson_with_ai, validate_lesson_file
from apps.schools.models import SchoolClass, EducationLevel

logger = logging.getLogger(__name__)


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

    if request.method == 'GET':
        return render(request, 'lessons/upload.html', {
            'school': school,
            'education_levels': EducationLevel.choices,
            'subject_types': SubjectType.choices,
        })

    # POST — traitement du formulaire
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

    title = request.POST.get('title', '').strip()
    subject = request.POST.get('subject', '').strip()
    subject_type = request.POST.get('subject_type', '')
    level = request.POST.get('level', '')
    level_detail = request.POST.get('level_detail', '').strip()

    if not title:
        errors['title'] = 'Titre requis.'
    if not subject:
        errors['subject'] = 'Matière requise.'
    if not subject_type:
        errors['subject_type'] = 'Type de matière requis.'
    if not level:
        errors['level'] = 'Niveau requis.'

    if errors:
        return render(request, 'lessons/upload.html', {
            'school': school,
            'education_levels': EducationLevel.choices,
            'subject_types': SubjectType.choices,
            'errors': errors,
            'post': request.POST,
        }, status=422)

    lesson = Lesson.objects.create(
        teacher=request.user,
        school=school,
        title=title,
        subject=subject,
        subject_type=subject_type,
        level=level,
        level_detail=level_detail,
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
