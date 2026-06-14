import logging
from datetime import timedelta

from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.core.student_auth import (
    authenticate_student, login_student, logout_student, student_required,
)
from apps.lessons.models import LessonDeployment, LessonStatus
from apps.student_learning.models import LessonProgress

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
            if not prog:
                node_state, progress_pct = 'not_started', 0
            elif prog.is_completed:
                node_state, progress_pct = 'completed', 100
            else:
                node_state = 'in_progress'
                blocks_total = len((dep.lesson.structured_content or {}).get('blocks', [])) or 1
                progress_pct = min(int(prog.last_block_index / blocks_total * 100), 99)

            lessons_data.append({
                'lesson': dep.lesson,
                'node_state': node_state,
                'progress_pct': progress_pct,
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

@student_required
def learn_lesson_stub(request, lesson_id):
    return render(request, 'learn/stub.html', {'student': request.student, 'title': 'Leçon', 'phase': 5})


@student_required
def learn_quiz_stub(request, lesson_id):
    return render(request, 'learn/stub.html', {'student': request.student, 'title': 'Quiz', 'phase': 6})


@student_required
def learn_flashcards_stub(request):
    return render(request, 'learn/stub.html', {'student': request.student, 'title': 'Flashcards', 'phase': 8})


@student_required
def learn_profile_stub(request):
    return render(request, 'learn/stub.html', {'student': request.student, 'title': 'Mon Profil', 'phase': 9})
