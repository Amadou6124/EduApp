"""
Portail Professeur — apps/teachers/
Namespace URL : teacher
"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.mixins import get_school, get_active_role, teacher_required
from apps.schools.models import ClassSubject, Note, SchoolClass, SchoolYear, Period
from apps.schools.periods import periods_for_class, periods_for_student, resolve_active_period
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

    # Période active PAR classe (selon son cycle) — un prof peut couvrir 2 cycles.
    class_period = {
        sc.pk: resolve_active_period(periods_for_class(sc, active_year))
        for sc in classes
    }
    active_period = next((p for p in class_period.values() if p), None)  # entête / repr.

    notes_per_class: dict[int, int] = {}
    for sc in classes:
        p = class_period.get(sc.pk)
        if not p:
            continue
        notes_per_class[sc.pk] = (
            Note.objects.filter(
                class_subject__teacher=user,
                class_subject__school_class_id=sc.pk,
                class_subject__is_active=True,
                period=p, is_cancelled=False,
            ).values('student').distinct().count()
        )

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

    # ── « À suivre » : élèves en difficulté agrégés sur toutes mes classes ──
    from .services import get_class_difficulty_report, LEVEL_CRITICAL, LEVEL_WARNING
    total_critical = total_warning = 0
    struggling = []
    for sc in classes:
        sc_period = class_period.get(sc.pk)
        if not sc_period:
            continue
        for r in get_class_difficulty_report(user, sc, sc_period):
            if r['level'] == LEVEL_CRITICAL:
                total_critical += 1
            elif r['level'] == LEVEL_WARNING:
                total_warning += 1
            else:
                continue
            weak = min(
                (sd for sd in r['scores'].values() if sd['score'] is not None),
                key=lambda sd: sd['score'], default=None,
            )
            struggling.append({
                'student': r['student'],
                'class':   sc,
                'score':   r['global_score'],
                'level':   r['level'],
                'trend':   r['trend'],
                'subject': weak['subject'] if weak else '',
            })
    struggling.sort(key=lambda s: s['score'] if s['score'] is not None else 99)
    top_struggling = struggling[:3]

    # ── « À saisir » : état de la saisie + classes à compléter ──
    saisie_open      = any(p and p.is_notes_open for p in class_period.values())
    classes_complete = sum(1 for c in class_cards if c['notes_pct'] >= 100)

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
        'saisie_open':         saisie_open,
        'classes_complete':    classes_complete,
        'total_critical':      total_critical,
        'total_warning':       total_warning,
        'top_struggling':      top_struggling,
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

    # Date d'émargement : aujourd'hui par défaut, jamais dans le futur.
    try:
        selected_date = datetime.strptime(request.GET.get('date', ''), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = today
    if selected_date > today:
        selected_date = today

    all_class_ids = _teacher_class_ids(user, school)

    classes = list(
        SchoolClass.objects
        .filter(pk__in=all_class_ids, school=school, is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .order_by('level', 'name')
    )

    # Absences notées par classe à la date choisie (1 requête). Purement factuel :
    # sans emploi du temps, on ne peut pas savoir quelles classes « doivent »
    # être émargées — on n'affiche donc ni obligation ni « en attente ».
    counts = {
        r['school_class_id']: r['n']
        for r in (Attendance.objects
                  .filter(school=school, school_class_id__in=all_class_ids, date=selected_date)
                  .values('school_class_id')
                  .annotate(n=Count('id')))
    }

    class_items = [
        {
            'class':         sc,
            'student_count': sc.student_count,
            'absent_count':  counts.get(sc.pk, 0),
        }
        for sc in classes
    ]

    is_today = selected_date == today
    return render(request, 'teachers/attendance_list.html', {
        'school':         school,
        'class_items':    class_items,
        'selected_date':  selected_date,
        'date_label':     _date_label(selected_date),
        'is_today':       is_today,
        'is_yesterday':   selected_date == today - timedelta(days=1),
        'prev_date':      (selected_date - timedelta(days=1)).isoformat(),
        'next_date':      None if is_today else (selected_date + timedelta(days=1)).isoformat(),
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
                    url=reverse('parent:dashboard'),
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
    from apps.schools.services.bulletin_calculator import BulletinCalculator, round2

    user   = request.user
    school = get_school(request)
    class_ids = _teacher_class_ids(user, school)

    student = get_object_or_404(Student, pk=student_id, school=school, is_active=True)
    if student.school_class_id not in class_ids:
        return HttpResponse(status=403)

    # Périodes du cycle de l'élève + période affichée (commutable via ?period=)
    today = date_cls.today()
    active_year = school.school_years.filter(is_active=True).first()
    periods = list(periods_for_student(student, active_year))

    active_period = None
    if periods:
        requested = request.GET.get('period')
        if requested:
            active_period = next((p for p in periods if str(p.pk) == requested), None)
        if not active_period:
            active_period = (
                next((p for p in periods if p.is_notes_open), None)
                # période couvrant aujourd'hui — seulement si elle est datée
                or next((p for p in periods if p.start_date and p.end_date
                         and p.start_date <= today <= p.end_date), None)
                or periods[0]
            )

    # Matières du prof dans la classe de l'élève
    my_subjects = list(
        ClassSubject.objects
        .filter(school_class=student.school_class, teacher=user, is_active=True)
        .select_related('subject')
        .order_by('order', 'subject__name')
    )

    # Notes de l'élève pour ces matières dans la période affichée
    notes_by_cs: dict[int, list] = {}
    if active_period and my_subjects:
        cs_ids = [cs.pk for cs in my_subjects]
        for n in (Note.objects
                  .filter(class_subject_id__in=cs_ids, student=student,
                          period=active_period, is_cancelled=False)
                  .order_by('position')):
            notes_by_cs.setdefault(n.class_subject_id, []).append(n)

    # Moyenne par matière = formule officielle du bulletin (source unique) →
    # cohérent avec la saisie et le bulletin, jamais une moyenne « à plat ».
    calc = BulletinCalculator()
    subject_notes = []
    for cs in my_subjects:
        by_pos = {n.position: n for n in notes_by_cs.get(cs.pk, [])}
        note_classe = by_pos.get(1)
        note_compo  = by_pos.get(2)
        raw = calc.calculate_subject_average([note_classe, note_compo], cs.max_grade)
        subject_notes.append({
            'cs':          cs,
            'note_classe': note_classe,
            'note_compo':  note_compo,
            'avg':         round2(raw) if raw is not None else None,
        })

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
        'periods':       periods,
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
        LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_INSUFFICIENT,
    )

    user   = request.user
    school = get_school(request)

    active_year = school.school_years.filter(is_active=True).first()

    class_ids = _teacher_class_ids(user, school)
    classes = list(
        SchoolClass.objects
        .filter(pk__in=class_ids, school=school, is_active=True)
        .order_by('level', 'name')
    )

    classes_data = []
    total_critical = total_warning = total_insufficient = 0
    active_period = None  # période représentative (entête) : 1re classe qui en a une

    for sc in classes:
        # Période active du cycle de CETTE classe (compositions / trimestres).
        period = resolve_active_period(periods_for_class(sc, active_year))
        if active_period is None:
            active_period = period
        report = get_class_difficulty_report(user, sc, period) if period else []

        critical     = [r for r in report if r['level'] == LEVEL_CRITICAL]
        warning      = [r for r in report if r['level'] == LEVEL_WARNING]
        insufficient = [r for r in report if r['level'] == LEVEL_INSUFFICIENT]

        total_critical     += len(critical)
        total_warning      += len(warning)
        total_insufficient += len(insufficient)

        classes_data.append({
            'school_class':       sc,
            'critical_students':  critical,
            'warning_students':   warning,
            'critical_count':     len(critical),
            'warning_count':      len(warning),
            'insufficient_count': len(insufficient),
            'flagged_count':      len(critical) + len(warning),
        })

    # Classes les plus critiques d'abord.
    classes_data.sort(key=lambda c: (-c['critical_count'], -c['warning_count']))

    return render(request, 'teachers/difficulty_dashboard.html', {
        'classes_data':       classes_data,
        'total_critical':     total_critical,
        'total_warning':      total_warning,
        'total_insufficient': total_insufficient,
        'total_flagged':      total_critical + total_warning,
        'active_period':      active_period,
    })


@login_required
@teacher_required
def difficulty_class(request, class_id):
    from .services import (
        get_class_difficulty_report,
        LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_INSUFFICIENT, LEVEL_GOOD,
    )

    user   = request.user
    school = get_school(request)
    class_ids = _teacher_class_ids(user, school)

    school_class = get_object_or_404(SchoolClass, pk=class_id, school=school, is_active=True)
    if school_class.pk not in class_ids:
        return HttpResponse(status=403)

    active_year   = school.school_years.filter(is_active=True).first()
    # Périodes du cycle de CETTE classe (compositions / trimestres selon le cycle).
    active_period = resolve_active_period(periods_for_class(school_class, active_year))

    # On ignore les élèves sans aucune donnée (level None).
    report_full = [
        r for r in (get_class_difficulty_report(user, school_class, active_period)
                    if active_period else [])
        if r['level'] is not None
    ]

    active_filter = request.GET.get('level', 'all')
    valid_filters = {LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_INSUFFICIENT, LEVEL_GOOD}
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
        'all':          len(report_full),
        'critical':     sum(1 for r in report_full if r['level'] == LEVEL_CRITICAL),
        'warning':      sum(1 for r in report_full if r['level'] == LEVEL_WARNING),
        'insufficient': sum(1 for r in report_full if r['level'] == LEVEL_INSUFFICIENT),
        'good':         sum(1 for r in report_full if r['level'] == LEVEL_GOOD),
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
    # Période active du cycle de la classe (via le class_subject).
    period = resolve_active_period(periods_for_class(class_subject.school_class, active_year))
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


# ─────────────────────────────────────────────────────────────
# Toutes mes observations
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def teacher_observations(request):
    from .models import StudentObservation

    user = request.user

    raw_obs = list(
        StudentObservation.objects
        .filter(teacher=user)
        .select_related('student', 'student__school_class')
        .order_by('-created_at')
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

    return render(request, 'teachers/observations.html', {
        'observations': observations,
        'total_count':  len(observations),
    })


# ─────────────────────────────────────────────────────────────
# Mon emploi du temps + mes heures (Lot 3 — confiance du vacataire)
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def my_schedule(request):
    """Le prof voit SA semaine (lecture seule) + ses heures émargées du mois, avec le
    détail séance par séance → un vacataire peut VÉRIFIER ce qu'on lui paie.

    Lecture seule stricte : aucune écriture. Les chiffres viennent des mêmes services
    que la paie (compute_teacher_hours / compute_vacataire_pay) — donc cohérents à 100 %
    avec l'écran Salaires du directeur. Le prof ne peut rien modifier ici."""
    from apps.schools.views import _print_timetable_ctx
    from apps.accounting.models import (
        TeacherAttendance, EmployeeProfile, EmploymentType,
    )
    from apps.accounting.services import compute_teacher_hours, compute_vacataire_pay

    school  = get_school(request)
    teacher = request.user

    # Emploi du temps (dérivé de ses cours) — même moteur que l'impression.
    ctx = _print_timetable_ctx(school, teacher=teacher)

    ctx['pay'] = None
    if school.accounting_enabled:
        today = date.today()
        y, m = today.year, today.month

        profile = EmployeeProfile.objects.filter(
            membership__user=teacher, membership__school=school,
        ).first()
        is_vac = bool(profile and profile.employment_type == EmploymentType.VACATAIRE)

        # Détail des séances du mois (présent/remplacé/absent) — la preuve à vérifier.
        sessions = list(
            TeacherAttendance.objects
            .filter(school=school, teacher=teacher, date__year=y, date__month=m)
            .select_related('class_subject__subject', 'class_subject__school_class')
            .order_by('-date')
        )
        counts = {'present': 0, 'replaced': 0, 'absent': 0}
        for a in sessions:
            counts[a.status] = counts.get(a.status, 0) + 1

        amount = None
        if is_vac:
            row = compute_vacataire_pay(school, y, m).get(teacher.id)
            amount = row['amount'] if row else 0

        ctx['pay'] = {
            'ref':      date(y, m, 1),
            'hours':    compute_teacher_hours(school, y, m).get(teacher.id, 0),
            'counts':   counts,
            'sessions': sessions,
            'is_vacataire': is_vac,
            'amount':   amount,
        }

    ctx['page_title'] = 'Mon emploi du temps'
    return render(request, 'teachers/my_schedule.html', ctx)
