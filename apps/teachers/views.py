"""
Portail Professeur — apps/teachers/
Namespace URL : teacher
"""
from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect, render

from apps.core.mixins import get_school
from apps.schools.models import ClassSubject, Note, SchoolClass


def teacher_required(view_func):
    """Décorateur réservé aux enseignants (role='teacher') et superusers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != 'teacher' and not request.user.is_superuser:
            return redirect('notes:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


_JOURS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
_MOIS  = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
          'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']

LEVEL_BADGE = {
    'prescolaire':    'bg-purple-100 text-purple-700',
    'fondamental_1':  'bg-blue-100 text-blue-700',
    'fondamental_2':  'bg-indigo-100 text-indigo-700',
    'secondaire_gen': 'bg-green-100 text-green-700',
    'secondaire_pro': 'bg-teal-100 text-teal-700',
    'superieur':      'bg-orange-100 text-orange-700',
}

OBS_BADGE = {
    'behaviour': ('bg-orange-100 text-orange-700', 'Comportement'),
    'academic':  ('bg-blue-100 text-blue-700',     'Académique'),
    'health':    ('bg-red-100 text-red-700',        'Santé'),
    'other':     ('bg-gray-100 text-gray-600',      'Autre'),
}


# ─────────────────────────────────────────────────────────────
# Phase 3 — Dashboard professeur
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def teacher_dashboard(request):
    from .models import Attendance, StudentObservation

    user   = request.user
    school = get_school(request)
    today  = date.today()

    today_label = (
        f"{_JOURS[today.weekday()]} {today.day} {_MOIS[today.month - 1]} {today.year}"
    )

    # ── Année + période actives ────────────────────────
    active_year = school.school_years.filter(is_active=True).first()
    active_period = None
    if active_year:
        active_period = active_year.periods.filter(is_notes_open=True).first()
        if not active_period:
            active_period = active_year.periods.order_by('-order').first()

    # ── Classes du prof (assigné + délégué) ────────────
    assigned_ids = set(
        ClassSubject.objects
        .filter(teacher=user, is_active=True)
        .values_list('school_class_id', flat=True)
        .distinct()
    )
    delegated_ids = set(
        school.classes
        .filter(notes_delegates=user, is_active=True)
        .values_list('pk', flat=True)
    )
    all_class_ids = assigned_ids | delegated_ids

    # ── Classes avec mes matières + effectifs (1 requête) ─
    classes = list(
        SchoolClass.objects
        .filter(pk__in=all_class_ids, is_active=True)
        .prefetch_related(
            Prefetch(
                'class_subjects',
                queryset=ClassSubject.objects.filter(
                    teacher=user, is_active=True,
                ).select_related('subject').order_by('order', 'subject__name'),
                to_attr='my_subjects',
            )
        )
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .order_by('level', 'name')
    )

    # ── Progression notes par classe (1 requête) ───────
    notes_per_class: dict[int, int] = {}
    if active_period and all_class_ids:
        for row in (
            Note.objects
            .filter(
                class_subject__teacher=user,
                class_subject__school_class_id__in=all_class_ids,
                class_subject__is_active=True,
                period=active_period,
                is_cancelled=False,
            )
            .values('class_subject__school_class_id')
            .annotate(noted=Count('student', distinct=True))
        ):
            notes_per_class[row['class_subject__school_class_id']] = row['noted']

    # ── Stats globales ─────────────────────────────────
    total_students = sum(c.student_count for c in classes)
    total_noted    = sum(notes_per_class.values())
    notes_pct      = round(total_noted / total_students * 100) if total_students else 0

    # ── Absences aujourd'hui (1 requête) ──────────────
    absences_today = (
        Attendance.objects.filter(
            school=school,
            school_class_id__in=all_class_ids,
            date=today,
            status__in=['absent', 'late'],
        ).count()
        if all_class_ids else 0
    )

    # ── 3 dernières observations (1 requête) ──────────
    raw_obs = list(
        StudentObservation.objects
        .filter(teacher=user)
        .select_related('student')
        .order_by('-created_at')[:3]
    )
    recent_observations = [
        {
            'obs': o,
            'badge_css': OBS_BADGE.get(o.observation_type, OBS_BADGE['other'])[0],
            'badge_label': OBS_BADGE.get(o.observation_type, OBS_BADGE['other'])[1],
            'excerpt': o.content[:60] + ('…' if len(o.content) > 60 else ''),
        }
        for o in raw_obs
    ]

    # ── Cards de classes enrichies ─────────────────────
    class_cards = []
    for sc in classes:
        noted = notes_per_class.get(sc.pk, 0)
        pct   = round(noted / sc.student_count * 100) if sc.student_count else 0
        class_cards.append({
            'class':        sc,
            'my_subjects':  sc.my_subjects,
            'student_count': sc.student_count,
            'notes_pct':    pct,
            'level_badge':  LEVEL_BADGE.get(sc.level, 'bg-gray-100 text-gray-600'),
        })

    avatar_bg, avatar_text = user.get_avatar_colors()
    first_name = user.full_name.split()[0] if user.full_name else '—'

    return render(request, 'teachers/dashboard.html', {
        'school':               school,
        'user':                 user,
        'first_name':           first_name,
        'avatar_bg':            avatar_bg,
        'avatar_text':          avatar_text,
        'active_year':          active_year,
        'active_period':        active_period,
        'today':                today,
        'today_label':          today_label,
        'class_cards':          class_cards,
        'nb_classes':           len(classes),
        'total_students':       total_students,
        'notes_pct':            notes_pct,
        'absences_today':       absences_today,
        'recent_observations':  recent_observations,
        'active_section':       'teacher_home',
    })


# ─────────────────────────────────────────────────────────────
# Phases 4-6 — stubs
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def attendance_list(request):
    # Phase 4 : liste des présences / absences
    return redirect('teacher:dashboard')


@login_required
@teacher_required
def attendance_class(request, class_id):
    # Phase 4 : saisie présences pour une classe
    return redirect('teacher:dashboard')


@login_required
@teacher_required
def attendance_save(request, class_id):
    # Phase 4 : sauvegarde en masse des présences
    return redirect('teacher:dashboard')


@login_required
@teacher_required
def teacher_students(request):
    # Phase 6 : liste des élèves du professeur (lecture seule)
    return redirect('teacher:dashboard')


@login_required
@teacher_required
def teacher_student_detail(request, student_id):
    # Phase 6 : fiche élève vue professeur
    return redirect('teacher:dashboard')


@login_required
@teacher_required
def observation_create(request, student_id):
    # Phase 6 : créer une observation sur un élève
    return redirect('teacher:dashboard')
