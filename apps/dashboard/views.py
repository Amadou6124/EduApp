"""
Dashboard V1 — Page d'accueil du portail administration.
Toutes les données calculées en UNE vue Django.
Zéro donnée fictive.
"""
from collections import defaultdict
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, Avg, Prefetch
from django.shortcuts import render

from apps.core.mixins import get_school
from apps.students.models import Student
from apps.schools.models import (
    SchoolClass, SchoolYear, Period, Bulletin, Note, ClassSubject, Subject,
)
from apps.payments.models import Payment
from apps.accounts.models import User


@login_required
def dashboard_view(request):
    """Page principale /dashboard/ — portail administration."""
    school = get_school(request)
    user = request.user

    # ── Protection rôle ────────────────────────────────────────────
    if user.role not in ('director', 'staff') and not user.is_superuser:
        return render(request, 'dashboard/dashboard.html', {
            'school': school,
            'no_access': True,
            'active_section': 'dashboard',
        })

    # ── Année / période active ─────────────────────────────────────
    active_year = (
        school.school_years.filter(is_active=True).first()
        or school.school_years.order_by('-start_date').first()
    )
    active_period = None
    if active_year:
        active_period = (
            active_year.periods.filter(is_notes_open=True).first()
            or active_year.periods.order_by('-order').first()
        )

    # ── SECTION 1 : KPIs ──────────────────────────────────────────
    kpis = _compute_kpis(school, active_year, active_period)

    # ── SECTION 2 : Alertes ───────────────────────────────────────
    alerts = _compute_alerts(school, active_year, active_period)

    # ── SECTION 3 : Graphiques ────────────────────────────────────
    charts = _compute_charts(school, active_year)

    # ── SECTION 4 : Santé par classe ───────────────────────────────
    class_health = _compute_class_health(school, active_period)

    # ── SECTION 5 : Activité récente ──────────────────────────────
    activity = _compute_activity(school)

    # ── Compteurs pour le header ────────────────────────────────────
    today = date.today()

    return render(request, 'dashboard/dashboard.html', {
        'school':        school,
        'active_year':   active_year,
        'active_period': active_period,
        'kpis':          kpis,
        'alerts':        alerts,
        'charts':        charts,
        'class_health':  class_health,
        'activity':      activity,
        'today':         today,
        'active_section': 'dashboard',
        'no_access':     False,
    })


# ─────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────

def _compute_kpis(school, active_year, active_period):
    """Calcule les 6 KPIs du tableau de bord."""
    # 1. Élèves inscrits
    student_count = Student.objects.filter(
        school=school, is_active=True,
    ).count()

    # 2. Classes actives
    class_count = school.classes.filter(is_active=True).count()

    # 3. Enseignants actifs (teacher role)
    teacher_count = User.objects.filter(
        school=school, role='teacher', is_active=True,
    ).count()

    # 4. Encaissé ce trimestre / période
    total_collected = 0
    if active_period:
        result = Payment.objects.filter(
            student__school=school,
            paid_at__date__gte=active_period.start_date,
            paid_at__date__lte=active_period.end_date,
            is_valid=True,
        ).aggregate(total=Sum('amount'))
        total_collected = result['total'] or 0

    # 5. Élèves avec impayés (solde > 0)
    unpaid_count = 0
    students = Student.objects.filter(school=school, is_active=True)
    for s in students:
        if s.get_balance_due() > 0:
            unpaid_count += 1

    # 6. Moyenne générale école
    school_avg = None
    if active_period:
        result = Note.objects.filter(
            class_subject__school_class__school=school,
            period=active_period,
            is_cancelled=False,
        ).aggregate(avg=Avg('value'))
        if result['avg']:
            school_avg = round(float(result['avg']), 2)

    return {
        'student_count':  student_count,
        'class_count':    class_count,
        'teacher_count':  teacher_count,
        'total_collected': total_collected,
        'unpaid_count':   unpaid_count,
        'school_avg':     school_avg,
    }


# ─────────────────────────────────────────────────────────────
# Alertes
# ─────────────────────────────────────────────────────────────

def _compute_alerts(school, active_year, active_period):
    """Calcule les alertes intelligentes."""
    alerts = []
    today = date.today()

    if not active_period:
        return alerts

    # ── CRITIQUE ──
    # Élèves avec impayés > 30 jours
    thirty_days_ago = today - timedelta(days=30)
    critical_unpaid = Student.objects.filter(
        school=school, is_active=True,
        enrolled_at__lte=thirty_days_ago,
    ).extra(
        where=["""
            (SELECT COALESCE(SUM(amount), 0)
             FROM payments_payment
             WHERE student_id = students_student.id
             AND is_valid = TRUE)
            < students_student.tuition_fee
        """]
    )
    unpaid_count = critical_unpaid.count()
    if unpaid_count > 0:
        alerts.append({
            'level': 'critical',
            'icon':  '🔴',
            'title': f'{unpaid_count} élève{"s" if unpaid_count > 1 else ""} avec solde impayé',
            'text':  'Ces élèves ont un solde impayé depuis plus de 30 jours.',
            'action_url': '/payments/',
            'action_text': 'Voir les paiements →',
        })

    # Notes manquantes à J-7 de fin de période
    if active_period.end_date and (active_period.end_date - today).days <= 7 and (active_period.end_date - today).days >= 0:
        classes = school.classes.filter(is_active=True)
        for sc in classes:
            cs_count = ClassSubject.objects.filter(school_class=sc, is_active=True).count()
            if cs_count == 0:
                continue
            students_cs = sc.students.filter(is_active=True, school=school).count()
            noted = Note.objects.filter(
                class_subject__school_class=sc,
                period=active_period,
                is_cancelled=False,
            ).values('student').distinct().count()
            missing = students_cs - noted
            if missing > 0:
                alerts.append({
                    'level': 'critical',
                    'icon':  '🔴',
                    'title': f'Notes manquantes dans {sc.name}',
                    'text':  f'{missing} élève{"s" if missing > 1 else ""} sans notes à J-7 de la fin.',
                    'action_url': f'/notes/{sc.pk}/{active_period.pk}/',
                    'action_text': 'Saisir →',
                })
                break  # Une alerte par classe suffit

    # ── ATTENTION ──
    # Élèves avec moyenne < 8/20
    low_students = Bulletin.objects.filter(
        period=active_period,
        school_class__school=school,
        is_cancelled=False,
        general_average__lt=8,
        general_average__isnull=False,
    ).select_related('student').count()
    if low_students > 0:
        alerts.append({
            'level': 'warning',
            'icon':  '🟡',
            'title': f'{low_students} élève{"s" if low_students > 1 else ""} en grande difficulté',
            'text':  'Moyenne générale < 8/20.',
            'action_url': '/bulletins/',
            'action_text': 'Voir les bulletins →',
        })

    # Saisie ouverte depuis > 30 jours
    if active_period.is_notes_open and active_period.start_date:
        days_open = (today - active_period.start_date).days
        if days_open > 30:
            alerts.append({
                'level': 'warning',
                'icon':  '🟡',
                'title': f'Saisie ouverte depuis {days_open} jours',
                'text':  'Envisagez de fermer la saisie dans les paramètres.',
                'action_url': '/settings/school-years/',
                'action_text': 'Paramètres →',
            })

    # ── INFO ──
    # Bulletins prêts à générer
    bulletins_ready = 0
    if active_period:
        classes = school.classes.filter(is_active=True)
        for sc in classes:
            students_count = sc.students.filter(is_active=True, school=school).count()
            existing = Bulletin.objects.filter(
                period=active_period, school_class=sc, is_cancelled=False,
            ).count()
            if students_count > existing:
                bulletins_ready += students_count - existing
    if bulletins_ready > 0:
        alerts.append({
            'level': 'info',
            'icon':  '🟢',
            'title': f'{bulletins_ready} bulletin{"s" if bulletins_ready > 1 else ""} à générer',
            'text':  'Génération des bulletins pour cette période.',
            'action_url': '/bulletins/',
            'action_text': 'Générer →',
        })

    return alerts


# ─────────────────────────────────────────────────────────────
# Graphiques
# ─────────────────────────────────────────────────────────────

def _compute_charts(school, active_year):
    """Calcule les données des graphiques Chart.js."""
    if not active_year:
        return {'enrollment_months': [], 'enrollment_data': [],
                'revenue_months': [], 'revenue_data': [], 'objective': 0}

    # Mois de l'année scolaire
    months = []
    cur = active_year.start_date
    while cur <= active_year.end_date:
        months.append(cur.strftime('%b %Y'))
        cur = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
        if cur.month == 1:
            cur = date(cur.year + 1, 1, 1)
    if not months:
        months = ['Oct', 'Nov', 'Déc', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin']

    # Inscriptions cumulées par mois
    enrollment_data = []
    cumulative = 0
    for m in months:
        month_num = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        count_this_month = Student.objects.filter(
            school=school, is_active=True,
            enrolled_at__month=m,
        ).count()
        cumulative += count_this_month
        enrollment_data.append(cumulative)

    # Revenus mensuels
    revenue_months = months
    revenue_data = []
    total_fees = Student.objects.filter(
        school=school, is_active=True,
    ).aggregate(total=Sum('tuition_fee'))['total'] or 0
    nb_months = max(len(months), 1)
    objective = round(total_fees / nb_months, -3)  # Arrondi aux milliers

    for m in months:
        monthly = Payment.objects.filter(
            student__school=school,
            paid_at__month=m,
            is_valid=True,
        ).aggregate(total=Sum('amount'))['total'] or 0
        revenue_data.append(float(monthly))

    return {
        'enrollment_months': months,
        'enrollment_data': enrollment_data,
        'revenue_months': revenue_months,
        'revenue_data': revenue_data,
        'objective': int(objective),
    }


# ─────────────────────────────────────────────────────────────
# Santé par classe
# ─────────────────────────────────────────────────────────────

def _compute_class_health(school, active_period):
    """Calcule les stats de santé par classe."""
    classes = list(
        school.classes.filter(is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .order_by('level', 'name')
    )

    rows = []
    for sc in classes:
        student_count = sc.student_count
        if student_count == 0:
            continue

        # Moyenne générale de la classe
        class_avg = None
        if active_period:
            result = Note.objects.filter(
                class_subject__school_class=sc,
                period=active_period,
                is_cancelled=False,
            ).aggregate(avg=Avg('value'))
            if result['avg']:
                class_avg = round(float(result['avg']), 2)

        # Taux de réussite (≥ 10/20)
        success_rate = None
        if active_period and class_avg:
            bulletins = Bulletin.objects.filter(
                period=active_period, school_class=sc, is_cancelled=False,
                general_average__isnull=False,
            )
            total = bulletins.count()
            if total > 0:
                admitted = bulletins.filter(general_average__gte=10).count()
                success_rate = round(admitted / total * 100, 1)

        # Taux de paiement
        total_fees = Student.objects.filter(
            school_class=sc, school=school, is_active=True,
        ).aggregate(total=Sum('tuition_fee'))['total'] or 0
        total_paid = Payment.objects.filter(
            student__school_class=sc,
            student__school=school,
            is_valid=True,
        ).aggregate(total=Sum('amount'))['total'] or 0
        payment_rate = round(total_paid / total_fees * 100, 1) if total_fees > 0 else 0

        # Statut global
        if class_avg and class_avg >= 12 and payment_rate > 80:
            status = 'good'
        elif class_avg and class_avg < 10 or payment_rate < 40:
            status = 'critical'
        else:
            status = 'warning'

        rows.append({
            'class': sc,
            'student_count': student_count,
            'avg': class_avg,
            'success_rate': success_rate,
            'payment_rate': payment_rate,
            'status': status,
        })

    return rows


# ─────────────────────────────────────────────────────────────
# Activité récente
# ─────────────────────────────────────────────────────────────

def _compute_activity(school):
    """Récupère les 10 dernières actions (payments, bulletins, notes, students)."""
    activity = []

    # Derniers paiements
    payments = list(
        Payment.objects.filter(student__school=school, is_valid=True)
        .select_related('student', 'collected_by')
        .order_by('-paid_at')[:5]
    )
    for p in payments:
        activity.append({
            'type': 'payment',
            'icon': '💳',
            'time': p.paid_at,
            'text': f'{p.student.full_name} — {int(p.amount):,} FCFA ({p.get_payment_method_display()})',
            'url':  '/payments/',
        })

    # Derniers bulletins générés
    bulletins = list(
        Bulletin.objects.filter(school_class__school=school, is_cancelled=False)
        .select_related('student', 'school_class', 'period')
        .order_by('-generated_at')[:5]
    )
    for b in bulletins:
        activity.append({
            'type': 'bulletin',
            'icon': '📄',
            'time': b.generated_at,
            'text': f'{b.school_class.name} — {b.period.name} — {b.student.full_name}',
            'url':  '/bulletins/',
        })

    # Dernières notes saisies
    notes = list(
        Note.objects.filter(class_subject__school_class__school=school)
        .select_related('student', 'class_subject__subject', 'class_subject__school_class', 'entered_by')
        .order_by('-entered_at')[:5]
    )
    for n in notes:
        activity.append({
            'type': 'note',
            'icon': '📝',
            'time': n.entered_at,
            'text': f'{n.entered_by.full_name} — {n.class_subject.subject.name} ({n.class_subject.school_class.name})',
            'url':  f'/notes/{n.class_subject.school_class_id}/{n.period_id}/',
        })

    # Derniers élèves inscrits
    students = list(
        Student.objects.filter(school=school)
        .order_by('-enrolled_at')[:5]
    )
    for s in students:
        activity.append({
            'type': 'student',
            'icon': '👤',
            'time': s.enrolled_at,
            'text': f'{s.full_name} — {s.school_class.name if s.school_class else "Aucune classe"}',
            'url':  '/students/',
        })

    # Trier par date décroissante et limiter à 10
    activity.sort(key=lambda x: x['time'], reverse=True)
    return activity[:10]