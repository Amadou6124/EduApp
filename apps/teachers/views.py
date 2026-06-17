"""
Portail Professeur — apps/teachers/
Namespace URL : teacher
"""
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.mixins import get_school, get_active_role, teacher_required
from apps.schools.models import ClassSubject, Note, SchoolClass, SchoolYear, Period
from apps.students.models import Student


_JOURS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
_MOIS  = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
          'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']


def _date_label(d):
    return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]} {d.year}"


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


def _relative_date_fr(dt):
    from django.utils import timezone
    now = timezone.now()
    diff = now - dt
    d = diff.days
    if d == 0:
        h = diff.seconds // 3600
        if h == 0:
            m = diff.seconds // 60
            return "à l'instant" if m < 2 else f"il y a {m}min"
        return f"il y a {h}h"
    if d == 1:
        return "hier"
    if d < 7:
        return f"il y a {d}j"
    w = d // 7
    if w < 5:
        return f"il y a {w}sem"
    return dt.strftime("%d/%m/%Y")


def _teacher_class_ids(user, school):
    """Retourne l'ensemble des PKs de classes du prof (assigné + délégué)."""
    assigned = set(
        ClassSubject.objects.filter(
            teacher=user,
            school_class__school=school,
            is_active=True,
        ).values_list('school_class_id', flat=True).distinct()
    )
    delegated = set(
        school.classes.filter(notes_delegates=user, is_active=True)
        .values_list('pk', flat=True)
    )
    return assigned | delegated


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

    active_year = school.school_years.filter(is_active=True).first()
    active_period = None
    if active_year:
        active_period = active_year.periods.filter(is_notes_open=True).first()
        if not active_period:
            active_period = active_year.periods.order_by('-order').first()

    all_class_ids = _teacher_class_ids(user, school)

    classes = list(
        SchoolClass.objects
        .filter(pk__in=all_class_ids, school=school, is_active=True)
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

    total_students = sum(c.student_count for c in classes)
    total_noted    = sum(notes_per_class.values())
    notes_pct      = round(total_noted / total_students * 100) if total_students else 0

    absences_today = (
        Attendance.objects.filter(
            school=school,
            school_class_id__in=all_class_ids,
            date=today,
            status__in=['absent', 'late'],
        ).count()
        if all_class_ids else 0
    )

    raw_obs = list(
        StudentObservation.objects
        .filter(teacher=user)
        .select_related('student')
        .order_by('-created_at')[:3]
    )
    recent_observations = [
        {
            'obs': o,
            'badge_css':   OBS_BADGE.get(o.observation_type, OBS_BADGE['other'])[0],
            'badge_label': OBS_BADGE.get(o.observation_type, OBS_BADGE['other'])[1],
            'excerpt':     o.content[:60] + ('…' if len(o.content) > 60 else ''),
        }
        for o in raw_obs
    ]

    class_cards = [
        {
            'class':         sc,
            'my_subjects':   sc.my_subjects,
            'student_count': sc.student_count,
            'notes_pct':     round(notes_per_class.get(sc.pk, 0) / sc.student_count * 100)
                             if sc.student_count else 0,
            'level_badge':   LEVEL_BADGE.get(sc.level, 'bg-gray-100 text-gray-600'),
        }
        for sc in classes
    ]

    avatar_bg, avatar_text = user.get_avatar_colors()
    first_name = user.full_name.split()[0] if user.full_name else '—'

    return render(request, 'teachers/dashboard.html', {
        'school':              school,
        'user':                user,
        'first_name':          first_name,
        'avatar_bg':           avatar_bg,
        'avatar_text':         avatar_text,
        'active_year':         active_year,
        'active_period':       active_period,
        'today':               today,
        'today_label':         _date_label(today),
        'class_cards':         class_cards,
        'nb_classes':          len(classes),
        'total_students':      total_students,
        'notes_pct':           notes_pct,
        'absences_today':      absences_today,
        'recent_observations': recent_observations,
        'active_section':      'teacher_home',
    })


# ─────────────────────────────────────────────────────────────
# Phase 4 — Absences
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def attendance_list(request):
    from .models import Attendance

    user   = request.user
    school = get_school(request)
    today  = date.today()

    all_class_ids = _teacher_class_ids(user, school)

    classes = list(
        SchoolClass.objects
        .filter(pk__in=all_class_ids, school=school, is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .order_by('level', 'name')
    )

    # Classes ayant au moins 1 enregistrement aujourd'hui (1 requête)
    done_today = set(
        Attendance.objects.filter(
            school=school,
            school_class_id__in=all_class_ids,
            date=today,
        ).values_list('school_class_id', flat=True).distinct()
    )

    class_items = [
        {
            'class':         sc,
            'student_count': sc.student_count,
            'done':          sc.pk in done_today,
            'level_badge':   LEVEL_BADGE.get(sc.level, 'bg-gray-100 text-gray-600'),
        }
        for sc in classes
    ]

    return render(request, 'teachers/attendance_list.html', {
        'school':         school,
        'class_items':    class_items,
        'today':          today,
        'today_label':    _date_label(today),
        'nb_done':        len(done_today),
        'nb_total':       len(class_items),
        'active_section': 'teacher_attendance',
    })


@login_required
@teacher_required
def attendance_class(request, class_id):
    from .models import Attendance
    from apps.students.models import Student

    user   = request.user
    school = get_school(request)

    school_class = get_object_or_404(SchoolClass, pk=class_id, school=school, is_active=True)

    has_access = (
        ClassSubject.objects.filter(
            school_class=school_class, teacher=user, is_active=True,
        ).exists()
        or school_class.notes_delegates.filter(pk=user.pk).exists()
    )
    if not has_access:
        return HttpResponse(status=403)

    date_str = request.GET.get('date', '')
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = date.today()

    students = list(
        Student.objects
        .filter(school_class=school_class, school=school, is_active=True)
        .order_by('full_name')
    )

    existing_records = Attendance.objects.filter(
        school=school, school_class=school_class, date=selected_date,
    )
    existing_map = {str(r.student_id): r.status for r in existing_records}

    students_data = [
        {
            'id':          s.pk,
            'name':        s.full_name,
            'short':       s.full_name.split()[0] if s.full_name else '—',
            'initials':    s.get_initials(),
            'avatar_bg':   s.get_avatar_colors()[0],
            'avatar_text': s.get_avatar_colors()[1],
        }
        for s in students
    ]

    return render(request, 'teachers/attendance_class.html', {
        'school':         school,
        'school_class':   school_class,
        'selected_date':  selected_date,
        'today_label':    _date_label(selected_date),
        'students_data':  students_data,
        'existing_map':   existing_map,
        'nb_students':    len(students),
        'active_section': 'teacher_attendance',
    })


@login_required
@teacher_required
@require_POST
def attendance_save(request, class_id):
    from .models import Attendance

    user   = request.user
    school = get_school(request)

    school_class = get_object_or_404(SchoolClass, pk=class_id, school=school, is_active=True)

    has_access = (
        ClassSubject.objects.filter(
            school_class=school_class, teacher=user, is_active=True,
        ).exists()
        or school_class.notes_delegates.filter(pk=user.pk).exists()
    )
    if not has_access:
        return HttpResponse(status=403)

    try:
        entries = json.loads(request.POST.get('absences', '[]'))
    except (json.JSONDecodeError, TypeError):
        return HttpResponse(status=400)

    date_str = request.POST.get('date', '')
    try:
        session_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        session_date = date.today()

    valid = {'absent', 'late'}
    absent_entries = [
        e for e in entries
        if isinstance(e, dict)
        and str(e.get('id', '')).isdigit()
        and e.get('status') in valid
    ]

    # Absents déjà enregistrés pour ce jour AVANT réécriture → évite de re-notifier
    existing_absent_ids = set(
        Attendance.objects.filter(
            school=school, school_class=school_class, date=session_date, status='absent',
        ).values_list('student_id', flat=True)
    )

    with transaction.atomic():
        Attendance.objects.filter(
            school=school, school_class=school_class, date=session_date,
        ).delete()
        if absent_entries:
            Attendance.objects.bulk_create([
                Attendance(
                    school=school,
                    school_class=school_class,
                    student_id=int(e['id']),
                    teacher=user,
                    date=session_date,
                    status=e['status'],
                )
                for e in absent_entries
            ], ignore_conflicts=True)

    # Notifier les parents des élèves NOUVELLEMENT absents (jamais bloquant)
    new_absent_ids = {
        int(e['id']) for e in absent_entries if e['status'] == 'absent'
    } - existing_absent_ids
    if new_absent_ids:
        try:
            from apps.notifications.services import notify_guardians
            from apps.notifications.models import NotificationCategory
            for st in Student.objects.filter(id__in=new_absent_ids, school=school):
                notify_guardians(
                    student=st,
                    category=NotificationCategory.ABSENCE,
                    title=f'{st.full_name} était absent(e)',
                    body=f'Absence enregistrée le {session_date}.',
                    url='/portal/parent/',
                )
        except Exception:
            pass

    nb  = len(absent_entries)
    msg = f"Présences de {school_class.name} enregistrées"
    if nb:
        msg += f" · {nb} absence{'s' if nb > 1 else ''} notée{'s' if nb > 1 else ''}"
    msg += "."

    resp = HttpResponse(status=200)
    resp['HX-Trigger'] = json.dumps({
        'showToast':       {'message': msg, 'type': 'success'},
        'attendance-saved': 'true',
    })
    return resp


# ─────────────────────────────────────────────────────────────
# Phases 5-6 — stubs
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def teacher_students(request):
    user   = request.user
    school = get_school(request)
    class_ids = _teacher_class_ids(user, school)

    classes = (SchoolClass.objects
               .filter(pk__in=class_ids, school=school, is_active=True)
               .prefetch_related(
                   Prefetch(
                       'students',
                       queryset=Student.objects.filter(is_active=True).annotate(
                           obs_count=Count(
                               'observations',
                               filter=Q(observations__teacher=user),
                           )
                       ).order_by('full_name'),
                   )
               )
               .order_by('level', 'name'))

    class_groups = []
    total_students = 0
    for sc in classes:
        students = list(sc.students.all())
        total_students += len(students)
        class_groups.append({
            'class': sc,
            'students': students,
            'level_badge': LEVEL_BADGE.get(sc.level, 'bg-gray-100 text-gray-600'),
            'names_json': json.dumps([s.full_name.lower() for s in students]),
        })

    return render(request, 'teachers/students_list.html', {
        'class_groups':   class_groups,
        'total_students': total_students,
    })


@login_required
@teacher_required
def teacher_student_detail(request, student_id):
    from .models import StudentObservation
    from datetime import date as date_cls

    user   = request.user
    school = get_school(request)
    class_ids = _teacher_class_ids(user, school)

    student = get_object_or_404(Student, pk=student_id, school=school, is_active=True)
    if student.school_class_id not in class_ids:
        return HttpResponse(status=403)

    # Période active
    today = date_cls.today()
    active_year = school.school_years.filter(is_active=True).first()
    active_period = None
    if active_year:
        active_period = (
            active_year.periods.filter(start_date__lte=today, end_date__gte=today).first()
            or active_year.periods.order_by('-order').first()
        )

    # Matières du prof dans la classe de l'élève
    my_subjects = list(
        ClassSubject.objects
        .filter(school_class=student.school_class, teacher=user, is_active=True)
        .select_related('subject')
        .order_by('order', 'subject__name')
    )

    # Notes de l'élève pour ces matières dans la période active
    notes_by_cs: dict[int, list] = {}
    if active_period and my_subjects:
        cs_ids = [cs.pk for cs in my_subjects]
        for n in (Note.objects
                  .filter(class_subject_id__in=cs_ids, student=student,
                          period=active_period, is_cancelled=False)
                  .order_by('position')):
            notes_by_cs.setdefault(n.class_subject_id, []).append(n)

    subject_notes = []
    for cs in my_subjects:
        notes = notes_by_cs.get(cs.pk, [])
        avg = None
        if notes:
            avg = round(sum(n.value for n in notes) / len(notes), 2)
        subject_notes.append({'cs': cs, 'notes': notes, 'avg': avg})

    # Observations du prof sur cet élève
    raw_obs = list(
        StudentObservation.objects
        .filter(teacher=user, student=student)
        .order_by('-created_at')[:30]
    )
    observations = [
        {
            'obs':         o,
            'badge_css':   OBS_BADGE.get(o.observation_type, OBS_BADGE['other'])[0],
            'badge_label': OBS_BADGE.get(o.observation_type, OBS_BADGE['other'])[1],
            'rel_date':    _relative_date_fr(o.created_at),
        }
        for o in raw_obs
    ]

    return render(request, 'teachers/student_detail.html', {
        'student':       student,
        'active_period': active_period,
        'subject_notes': subject_notes,
        'observations':  observations,
    })


@login_required
@teacher_required
@require_POST
def observation_create(request, student_id):
    from .models import StudentObservation

    user   = request.user
    school = get_school(request)
    class_ids = _teacher_class_ids(user, school)

    student = get_object_or_404(Student, pk=student_id, school=school, is_active=True)
    if student.school_class_id not in class_ids:
        return HttpResponse(status=403)

    obs_type = request.POST.get('observation_type', 'academic')
    if obs_type not in {'behaviour', 'academic', 'health', 'other'}:
        obs_type = 'academic'

    content = request.POST.get('content', '').strip()
    if not content:
        resp = HttpResponse(status=400)
        return resp

    is_private = request.POST.get('is_private', 'true').lower() not in ('false', '0', 'no')

    StudentObservation.objects.create(
        school=school,
        student=student,
        teacher=user,
        observation_type=obs_type,
        content=content,
        is_private=is_private,
    )

    msg = 'Note privée enregistrée.' if is_private else "Observation envoyée à l'administration."
    resp = HttpResponse(status=200)
    resp['HX-Trigger'] = json.dumps({
        'showToast':      {'message': msg, 'type': 'success'},
        'close-obs-panel': 'true',
    })
    return resp


# ─────────────────────────────────────────────────────────────
# Suivi des élèves en difficulté
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def difficulty_dashboard(request):
    from .services import (
        get_class_difficulty_report,
        LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_WATCH,
    )

    user   = request.user
    school = get_school(request)

    active_year = school.school_years.filter(is_active=True).first()
    active_period = None
    if active_year:
        active_period = (
            active_year.periods.filter(is_notes_open=True).first()
            or active_year.periods.order_by('-order').first()
        )

    class_ids = _teacher_class_ids(user, school)
    classes = list(
        SchoolClass.objects
        .filter(pk__in=class_ids, school=school, is_active=True)
        .order_by('level', 'name')
    )

    classes_data = []
    total_critical = 0
    total_warning  = 0

    for sc in classes:
        report = get_class_difficulty_report(user, sc, active_period) if active_period else []

        critical = sum(1 for r in report if r['level'] == LEVEL_CRITICAL)
        warning  = sum(1 for r in report if r['level'] == LEVEL_WARNING)
        watch    = sum(1 for r in report if r['level'] == LEVEL_WATCH)

        total_critical += critical
        total_warning  += warning

        classes_data.append({
            'school_class':      sc,
            'level_badge':       LEVEL_BADGE.get(sc.level, 'bg-gray-100 text-gray-600'),
            'report':            report,
            'critical_count':    critical,
            'warning_count':     warning,
            'watch_count':       watch,
            'total_struggling':  critical + warning + watch,
            'critical_students': [r for r in report if r['level'] == LEVEL_CRITICAL],
            'warning_students':  [r for r in report if r['level'] == LEVEL_WARNING],
            'watch_students':    [r for r in report if r['level'] == LEVEL_WATCH],
        })

    classes_data.sort(key=lambda c: -c['critical_count'])

    return render(request, 'teachers/difficulty_dashboard.html', {
        'classes_data':     classes_data,
        'total_critical':   total_critical,
        'total_warning':    total_warning,
        'total_struggling': sum(c['total_struggling'] for c in classes_data),
        'active_period':    active_period,
    })


@login_required
@teacher_required
def difficulty_class(request, class_id):
    from .services import (
        get_class_difficulty_report,
        LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_WATCH, LEVEL_GOOD,
    )

    user   = request.user
    school = get_school(request)
    class_ids = _teacher_class_ids(user, school)

    school_class = get_object_or_404(SchoolClass, pk=class_id, school=school, is_active=True)
    if school_class.pk not in class_ids:
        return HttpResponse(status=403)

    active_year = school.school_years.filter(is_active=True).first()
    active_period = None
    if active_year:
        active_period = (
            active_year.periods.filter(is_notes_open=True).first()
            or active_year.periods.order_by('-order').first()
        )

    report_full = (
        get_class_difficulty_report(user, school_class, active_period)
        if active_period else []
    )

    active_filter = request.GET.get('level', 'all')
    valid_filters = {LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_WATCH, LEVEL_GOOD}
    if active_filter in valid_filters:
        report = [r for r in report_full if r['level'] == active_filter]
    else:
        active_filter = 'all'
        report = report_full

    my_subjects = list(
        ClassSubject.objects
        .filter(school_class=school_class, teacher=user, is_active=True)
        .select_related('subject')
        .order_by('order', 'subject__name')
    )

    counts = {
        'all':      len(report_full),
        'critical': sum(1 for r in report_full if r['level'] == LEVEL_CRITICAL),
        'warning':  sum(1 for r in report_full if r['level'] == LEVEL_WARNING),
        'watch':    sum(1 for r in report_full if r['level'] == LEVEL_WATCH),
        'good':     sum(1 for r in report_full if r['level'] == LEVEL_GOOD),
    }

    return render(request, 'teachers/difficulty_class.html', {
        'school_class':  school_class,
        'level_badge':   LEVEL_BADGE.get(school_class.level, 'bg-gray-100 text-gray-600'),
        'report':        report,
        'period':        active_period,
        'active_filter': active_filter,
        'my_subjects':   my_subjects,
        'counts':        counts,
    })


@login_required
@teacher_required
@require_POST
def quick_assessment_save(request):
    from .models import QuickAssessment
    from datetime import datetime as _dt, date as _date

    user   = request.user
    school = get_school(request)

    try:
        student_id       = int(request.POST.get('student_id', ''))
        class_subject_id = int(request.POST.get('class_subject_id', ''))
        value            = Decimal(request.POST.get('value', '').strip())
    except (ValueError, TypeError, InvalidOperation):
        return HttpResponse(status=400)

    try:
        max_value = Decimal(request.POST.get('max_value', '20').strip())
        if max_value < Decimal('1'):
            max_value = Decimal('20')
    except (ValueError, TypeError, InvalidOperation):
        max_value = Decimal('20')

    assessment_type = request.POST.get('assessment_type', 'oral')
    valid_types = {t[0] for t in QuickAssessment.AssessmentType.choices}
    if assessment_type not in valid_types:
        assessment_type = 'oral'

    note_text = request.POST.get('note', '').strip()[:200]

    try:
        assessed_at = _dt.strptime(
            request.POST.get('assessed_at', '').strip(), '%Y-%m-%d'
        ).date()
    except (ValueError, TypeError):
        assessed_at = _date.today()

    if not (Decimal('0') <= value <= max_value):
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({
            'showToast': {
                'message': f'La note doit être entre 0 et {max_value}.',
                'type': 'error',
            },
        })
        return resp

    class_subject = get_object_or_404(
        ClassSubject,
        pk=class_subject_id,
        teacher=user,
        is_active=True,
        school_class__school=school,
    )

    student = get_object_or_404(
        Student,
        pk=student_id,
        school=school,
        is_active=True,
        school_class=class_subject.school_class,
    )

    active_year = school.school_years.filter(is_active=True).first()
    if not active_year:
        return HttpResponse(status=400)
    period = (
        active_year.periods.filter(is_notes_open=True).first()
        or active_year.periods.order_by('-order').first()
    )
    if not period:
        return HttpResponse(status=400)

    QuickAssessment.objects.create(
        teacher=user,
        student=student,
        class_subject=class_subject,
        period=period,
        assessment_type=assessment_type,
        value=value,
        max_value=max_value,
        note=note_text,
        assessed_at=assessed_at,
    )

    from .services import compute_difficulty_score
    score_dict = compute_difficulty_score(student, user, class_subject, period)
    score_display = f"{score_dict['score']}/20" if score_dict['score'] is not None else '—'

    resp = HttpResponse(status=200)
    resp['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'Évaluation enregistrée · {score_display}',
            'type': 'success',
        },
        'close-qa-panel': 'true',
        'score-updated': {
            'student_id':       student.pk,
            'class_subject_id': class_subject.pk,
            'score': str(score_dict['score']) if score_dict['score'] is not None else None,
            'level': score_dict['level'],
            'trend': score_dict['trend'],
        },
    })
    return resp


# ── Notifications enseignant ──────────────────────────────────────────────

@login_required
@teacher_required
def teacher_notifications(request):
    """Liste des notifications de l'enseignant, groupées par date."""
    from datetime import timedelta
    from django.utils import timezone
    today     = timezone.now().date()
    yesterday = today - timedelta(days=1)
    week_ago  = today - timedelta(days=7)

    notifs = list(request.user.notifications.all())
    for n in notifs:
        d = n.created_at.date()
        if d == today:
            n.date_group = "Aujourd'hui"
        elif d == yesterday:
            n.date_group = "Hier"
        elif d >= week_ago:
            n.date_group = "Cette semaine"
        else:
            n.date_group = "Plus ancien"

    return render(request, 'teachers/notifications.html', {
        'notifications': notifs,
        'unread_count': sum(1 for n in notifs if not n.is_read),
    })


@login_required
@teacher_required
def teacher_notif_open(request, notif_id):
    """Marque lu puis redirige vers la cible de la notification."""
    from apps.notifications.models import Notification
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
    return redirect(notif.url or 'teacher:notifications')


@login_required
@teacher_required
@require_POST
def teacher_notif_delete(request, notif_id):
    """Supprime une notification. Renvoie '' → la card disparaît (HTMX swap)."""
    from apps.notifications.models import Notification
    get_object_or_404(Notification, id=notif_id, recipient=request.user).delete()
    return HttpResponse('')


@login_required
@teacher_required
@require_POST
def teacher_notif_read_all(request):
    """Marque toutes les notifications comme lues."""
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('teacher:notifications')


@login_required
@teacher_required
@require_POST
def teacher_notif_clear(request):
    """Supprime toutes les notifications de l'enseignant."""
    request.user.notifications.all().delete()
    return redirect('teacher:notifications')
