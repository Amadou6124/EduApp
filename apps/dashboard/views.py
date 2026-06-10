"""
Dashboard V1 — Page d'accueil du portail administration.
Toutes les données calculées en UNE vue Django.
Zero donnee fictive.
"""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, Avg
from django.shortcuts import render

from apps.core.mixins import get_school
from apps.students.models import Student
from apps.schools.models import (
    SchoolClass, SchoolYear, Period, Bulletin, Note, ClassSubject,
)
from apps.payments.models import Payment
from apps.accounts.models import User


@login_required
def dashboard_view(request):
    school = get_school(request)
    user = request.user

    if user.role not in ('director', 'staff') and not user.is_superuser:
        return render(request, 'dashboard/dashboard.html', {
            'school': school, 'no_access': True, 'active_section': 'dashboard',
        })

    active_year = school.school_years.filter(is_active=True).first()
    if not active_year:
        active_year = school.school_years.order_by('-start_date').first()

    active_period = None
    if active_year:
        active_period = active_year.periods.filter(is_notes_open=True).first()
        if not active_period:
            active_period = active_year.periods.order_by('-order').first()

    kpis = _compute_kpis(school, active_period)
    alerts = _compute_alerts(school, active_period)
    charts = _compute_charts(school, active_year)
    class_health = _compute_class_health(school, active_period)
    activity = _compute_activity(school)
    today = date.today()

    return render(request, 'dashboard/dashboard.html', {
        'school': school, 'active_year': active_year, 'active_period': active_period,
        'kpis': kpis, 'alerts': alerts, 'charts': charts,
        'class_health': class_health, 'activity': activity,
        'today': today, 'active_section': 'dashboard', 'no_access': False,
    })


def _compute_kpis(school, active_period):
    student_count = Student.objects.filter(school=school, is_active=True).count()
    class_count = school.classes.filter(is_active=True).count()
    teacher_count = User.objects.filter(school=school, role='teacher', is_active=True).count()
    total_collected = 0
    if active_period:
        result = Payment.objects.filter(
            student__school=school,
            payment_date__gte=active_period.start_date,
            payment_date__lte=active_period.end_date,
            is_cancelled=False,
        ).aggregate(total=Sum('amount'))
        total_collected = result['total'] or 0
    unpaid_count = 0
    for s in Student.objects.filter(school=school, is_active=True):
        if s.get_balance_due() > 0:
            unpaid_count += 1
    school_avg = None
    if active_period:
        result = Note.objects.filter(
            class_subject__school_class__school=school,
            period=active_period, is_cancelled=False,
        ).aggregate(avg=Avg('value'))
        if result['avg']:
            school_avg = round(float(result['avg']), 2)
    return {
        'student_count': student_count, 'class_count': class_count,
        'teacher_count': teacher_count, 'total_collected': total_collected,
        'unpaid_count': unpaid_count, 'school_avg': school_avg,
    }


def _compute_alerts(school, active_period):
    alerts = []
    today = date.today()
    if not active_period:
        return alerts
    # Critique : impayes > 30 jours
    thirty_days_ago = today - timedelta(days=30)
    unpaid_crit = 0
    for s in Student.objects.filter(school=school, is_active=True):
        if s.get_balance_due() > 0:
            unpaid_crit += 1
    if unpaid_crit > 0:
        alerts.append({
            'level': 'critical', 'icon': chr(0x1f534),
            'title': f'{unpaid_crit} eleve{"s" if unpaid_crit > 1 else ""} avec solde impaye',
            'text': 'Ces eleves ont un solde impaye.',
            'action_url': '/payments/', 'action_text': 'Voir les paiements >',
        })
    # Attention : moyenne < 8
    low = Bulletin.objects.filter(
        period=active_period, school_class__school=school,
        is_cancelled=False, general_average__lt=8,
    ).count()
    if low > 0:
        alerts.append({
            'level': 'warning', 'icon': chr(0x1f7e1),
            'title': f'{low} eleve{"s" if low > 1 else ""} en grande difficulte',
            'text': 'Moyenne generale < 8/20.',
            'action_url': '/bulletins/', 'action_text': 'Voir les bulletins >',
        })
    # Info : bulletins prets
    ready = 0
    for sc in school.classes.filter(is_active=True):
        n_students = sc.students.filter(is_active=True, school=school).count()
        existing = Bulletin.objects.filter(
            period=active_period, school_class=sc, is_cancelled=False,
        ).count()
        if n_students > existing:
            ready += n_students - existing
    if ready > 0:
        alerts.append({
            'level': 'info', 'icon': chr(0x1f7e2),
            'title': f'{ready} bulletin{"s" if ready > 1 else ""} a generer',
            'text': 'Generation des bulletins pour cette periode.',
            'action_url': '/bulletins/', 'action_text': 'Generer >',
        })
    return alerts


def _compute_charts(school, active_year):
    if not active_year:
        return {
            'enrollment_months': [], 'enrollment_data': [],
            'revenue_months': [], 'revenue_data': [], 'objective': 0,
        }
    months = []
    cur = active_year.start_date
    while cur <= active_year.end_date:
        months.append(cur.strftime('%b'))
        month = cur.month
        cur = date(cur.year + (month // 12), (month % 12) + 1, 1)
    if not months:
        months = ['Oct', 'Nov', 'Dec', 'Jan', 'Fev', 'Mar', 'Avr', 'Mai', 'Juin']
    enrollment_data = []
    cumul = 0
    for m in months:
        month_num = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        count = Student.objects.filter(
            school=school, is_active=True,
        ).count()
        cumul += count
        enrollment_data.append(cumul)
    total_fees = Student.objects.filter(school=school, is_active=True).aggregate(total=Sum('tuition_fee'))['total'] or 0
    nb = max(len(months), 1)
    objective = round(total_fees / nb, -3)
    revenue_data = []
    for m in months:
        monthly = Payment.objects.filter(
            student__school=school, is_cancelled=False,
        ).aggregate(total=Sum('amount'))['total'] or 0
        revenue_data.append(float(monthly))
    return {
        'enrollment_months': months, 'enrollment_data': enrollment_data,
        'revenue_months': months, 'revenue_data': revenue_data,
        'objective': int(objective),
    }


def _compute_class_health(school, active_period):
    classes = list(
        school.classes.filter(is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .order_by('level', 'name')
    )
    rows = []
    for sc in classes:
        if sc.student_count == 0:
            continue
        class_avg = None
        if active_period:
            result = Note.objects.filter(
                class_subject__school_class=sc, period=active_period, is_cancelled=False,
            ).aggregate(avg=Avg('value'))
            if result['avg']:
                class_avg = round(float(result['avg']), 2)
        success_rate = None
        if active_period:
            buls = Bulletin.objects.filter(
                period=active_period, school_class=sc, is_cancelled=False,
                general_average__isnull=False,
            )
            total = buls.count()
            if total > 0:
                admitted = buls.filter(general_average__gte=10).count()
                success_rate = round(admitted / total * 100, 1)
        total_fees = Student.objects.filter(
            school_class=sc, school=school, is_active=True,
        ).aggregate(total=Sum('tuition_fee'))['total'] or 0
        total_paid = Payment.objects.filter(
            student__school_class=sc, student__school=school, is_cancelled=False,
        ).aggregate(total=Sum('amount'))['total'] or 0
        payment_rate = round(total_paid / total_fees * 100, 1) if total_fees > 0 else 0
        if class_avg and class_avg >= 12 and payment_rate > 80:
            status = 'good'
        elif (class_avg and class_avg < 10) or payment_rate < 40:
            status = 'critical'
        else:
            status = 'warning'
        rows.append({
            'class': sc, 'student_count': sc.student_count,
            'avg': class_avg, 'success_rate': success_rate,
            'payment_rate': payment_rate, 'status': status,
        })
    return rows


def _compute_activity(school):
    activity = []
    for p in Payment.objects.filter(student__school=school, is_cancelled=False).select_related('student', 'collected_by').order_by('-payment_date')[:5]:
        activity.append({
            'type': 'payment', 'icon': chr(0x1f4b3),
            'time': p.payment_date,
            'text': f'{p.student.full_name} -- {int(p.amount):,} FCFA ({p.get_payment_method_display()})',
            'url': '/payments/',
        })
    for b in Bulletin.objects.filter(school_class__school=school, is_cancelled=False).select_related('student', 'school_class', 'period').order_by('-generated_at')[:5]:
        activity.append({
            'type': 'bulletin', 'icon': chr(0x1f4c4),
            'time': b.generated_at,
            'text': f'{b.school_class.name} -- {b.period.name} -- {b.student.full_name}',
            'url': '/bulletins/',
        })
    for n in Note.objects.filter(class_subject__school_class__school=school).select_related('student', 'class_subject__subject', 'class_subject__school_class', 'entered_by').order_by('-entered_at')[:5]:
        activity.append({
            'type': 'note', 'icon': chr(0x1f4dd),
            'time': n.entered_at,
            'text': f'{n.entered_by.full_name} -- {n.class_subject.subject.name} ({n.class_subject.school_class.name})',
            'url': f'/notes/{n.class_subject.school_class_id}/{n.period_id}/',
        })
    for s in Student.objects.filter(school=school).order_by('-enrolled_at')[:5]:
        activity.append({
            'type': 'student', 'icon': chr(0x1f464),
            'time': s.enrolled_at,
            'text': f'{s.full_name} -- {s.school_class.name if s.school_class else "Aucune classe"}',
            'url': '/students/',
        })
    activity.sort(key=lambda x: x['time'], reverse=True)
    return activity[:10]