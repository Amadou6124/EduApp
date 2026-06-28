"""
Dashboard V1 — Page d'accueil du portail administration.
Toutes les données calculées en UNE vue Django.
Zero donnee fictive.
"""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.urls import reverse

from apps.core.constants import (
    PASS_THRESHOLD, GOOD_AVERAGE_THRESHOLD,
    PAYMENT_GOOD_THRESHOLD, PAYMENT_CRITICAL_THRESHOLD,
)
from django.core.cache import cache
from django.db.models import Count, Sum, Q, Avg, Subquery, OuterRef, F, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import render, redirect

from apps.core.mixins import get_school
from apps.students.models import Student
from apps.schools.models import (
    SchoolClass, SchoolYear, Period, Bulletin, Note, ClassSubject,
)
from apps.payments.models import Payment
from apps.accounts.models import User, UserRole


def invalidate_dashboard_cache(school):
    """Invalide toutes les clés de cache dashboard pour une école."""
    from apps.schools.models import SchoolYear
    for year in SchoolYear.objects.filter(school=school).prefetch_related('periods'):
        for period in year.periods.all():
            cache.delete(f'dashboard_{school.id}_{year.id}_{period.id}')
        cache.delete(f'dashboard_{school.id}_{year.id}_none')
    cache.delete(f'dashboard_{school.id}_none_none')


@login_required
def dashboard_view(request):
    if request.user.role == UserRole.TEACHER:
        return redirect('teacher:dashboard')
    school = get_school(request)
    user = request.user

    if user.role not in (UserRole.DIRECTOR, UserRole.STAFF) and not user.is_superuser:
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

    period_id = active_period.id if active_period else 'none'
    year_id   = active_year.id   if active_year   else 'none'
    cache_key = f'dashboard_{school.id}_{year_id}_{period_id}'

    computed = cache.get(cache_key)
    if computed is None:
        kpis         = _compute_kpis(school, active_period)
        alerts       = _compute_alerts(school, active_period, kpis['unpaid_count'])
        charts       = _compute_charts(school, active_year)
        class_health = _compute_class_health(school, active_period)
        activity     = _compute_activity(school)
        computed = {
            'kpis': kpis, 'alerts': alerts, 'charts': charts,
            'class_health': class_health, 'activity': activity,
        }
        cache.set(cache_key, computed, 60 * 5)

    # Permissions per-école : directeur/superuser = tout ; staff = selon StaffPermission.
    if request.role == UserRole.DIRECTOR or request.user.is_superuser:
        can_pay, can_stu = True, True
    else:
        perm = getattr(request.user, 'staff_permission', None)
        can_pay = bool(perm and perm.can_view_payments)
        can_stu = bool(perm and perm.can_view_students)

    # Redaction PER-REQUÊTE (hors cache partagé école) — ne jamais envoyer au
    # client une donnée que ce staff n'a pas le droit de voir.
    kpis   = dict(computed['kpis'])
    alerts = list(computed['alerts'])
    charts = dict(computed['charts'])
    if not can_pay:
        kpis['total_collected']  = None
        kpis['unpaid_count']     = None
        alerts = [a for a in alerts if a.get('category') != 'payments']
        charts['revenue_data']   = []
        charts['revenue_months'] = []
    if not can_stu:
        kpis['student_count']      = None
        charts['enrollment_data']   = []
        charts['enrollment_months'] = []

    return render(request, 'dashboard/dashboard.html', {
        'school': school, 'active_year': active_year, 'active_period': active_period,
        'today': date.today(), 'active_section': 'dashboard', 'no_access': False,
        'kpis': kpis, 'alerts': alerts, 'charts': charts,
        'class_health': computed['class_health'], 'activity': computed['activity'],
        'perms': {'can_view_payments': can_pay, 'can_view_students': can_stu},
    })


def _compute_kpis(school, active_period):
    student_count = Student.objects.filter(school=school, is_active=True).count()
    class_count = school.classes.filter(is_active=True).count()
    teacher_count = User.objects.filter(school=school, role=UserRole.TEACHER, is_active=True).count()
    total_collected = 0
    if active_period:
        result = Payment.objects.filter(
            student__school=school,
            payment_date__gte=active_period.start_date,
            payment_date__lte=active_period.end_date,
            is_cancelled=False,
        ).aggregate(total=Sum('amount'))
        total_collected = result['total'] or 0
    # Élèves avec solde dû (lot 6bis-A) — NOUVEAU modèle : fiches dont balance > 0
    # (somme des 3 familles par allocation). Les élèves SANS fiche ne sont pas comptés
    # (« inconnus », pas « impayés »). Le sous-ensemble URGENT = la liste rouge du lot 6
    # (tranches échues) ; ici on compte tout solde dû, cohérent avec le libellé « solde impayé ».
    from apps.finance.services import fee_accounts_annotated
    unpaid_count = fee_accounts_annotated(school=school).filter(balance__gt=0).count()
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


def _compute_alerts(school, active_period, unpaid_count=0):
    alerts = []
    if not active_period:
        return alerts
    if unpaid_count > 0:
        alerts.append({
            'level': 'critical', 'icon': 'alert-circle', 'category': 'payments',
            'title': f'{unpaid_count} eleve{"s" if unpaid_count > 1 else ""} avec solde impaye',
            'text': 'Ces eleves ont un solde impaye.',
            'action_url': reverse('payments:dashboard'), 'action_text': 'Voir les paiements >',
        })
    # Attention : moyenne < 8
    low = Bulletin.objects.filter(
        period=active_period, school_class__school=school,
        is_cancelled=False, general_average__lt=8,
    ).count()
    if low > 0:
        alerts.append({
            'level': 'warning', 'icon': 'alert-triangle',
            'title': f'{low} eleve{"s" if low > 1 else ""} en grande difficulte',
            'text': 'Moyenne generale < 8/20.',
            'action_url': reverse('bulletins:main'), 'action_text': 'Voir les bulletins >',
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
            'level': 'info', 'icon': 'info',
            'title': f'{ready} bulletin{"s" if ready > 1 else ""} a generer',
            'text': 'Generation des bulletins pour cette periode.',
            'action_url': reverse('bulletins:main'), 'action_text': 'Generer >',
        })
    return alerts


from calendar import monthrange

def _compute_charts(school, active_year):
    if not active_year:
        return {
            'enrollment_months': [], 'enrollment_data': [],
            'revenue_months': [], 'revenue_data': [], 'objective': 0,
        }

    # Generer la liste des mois entre start_date et end_date
    months = []
    cur_year = active_year.start_date.year
    cur_month = active_year.start_date.month
    end_year = active_year.end_date.year
    end_month = active_year.end_date.month

    while (cur_year < end_year) or (cur_year == end_year and cur_month <= end_month):
        months.append({
            'label': date(cur_year, cur_month, 1).strftime('%b'),
            'year': cur_year,
            'num': cur_month,
            'last_day': monthrange(cur_year, cur_month)[1],
        })
        cur_month += 1
        if cur_month > 12:
            cur_month = 1
            cur_year += 1

    if not months:
        months = [
            {'label': 'Oct', 'year': 2024, 'num': 10, 'last_day': 31},
            {'label': 'Nov', 'year': 2024, 'num': 11, 'last_day': 30},
        ]

    # Graphique 1 : Inscriptions cumulées par mois (1 requête)
    enrollment_map = {
        (row['month'].year, row['month'].month): row['count']
        for row in Student.objects.filter(
            school=school, is_active=True,
            enrolled_at__date__gte=active_year.start_date,
            enrolled_at__date__lte=active_year.end_date,
        )
        .annotate(month=TruncMonth('enrolled_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    }
    # Cumul : chaque mois affiche le total depuis le début d'année
    cumul = 0
    # Élèves inscrits avant le début de l'année scolaire
    cumul = Student.objects.filter(
        school=school, is_active=True,
        enrolled_at__date__lt=active_year.start_date,
    ).count()
    enrollment_data = []
    for m in months:
        cumul += enrollment_map.get((m['year'], m['num']), 0)
        enrollment_data.append(cumul)

    # Graphique 2 : Revenus mensuels (1 requête)
    revenue_map = {
        (row['month'].year, row['month'].month): float(row['total'])
        for row in Payment.objects.filter(
            student__school=school,
            is_cancelled=False,
            payment_date__gte=active_year.start_date,
            payment_date__lte=active_year.end_date,
        )
        .annotate(month=TruncMonth('payment_date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    }
    revenue_data = [revenue_map.get((m['year'], m['num']), 0.0) for m in months]

    # Objectif mensuel — NOUVEAU modèle (lot 6bis-A) : dû réel des fiches (3 familles),
    # pas tuition_fee. Les élèves sans fiche ne gonflent/sous-comptent pas l'objectif.
    from apps.finance.services import fee_accounts_annotated
    total_fees = fee_accounts_annotated(school=school).aggregate(t=Sum('due'))['t'] or 0
    nb = max(len(months), 1)
    objective = round(total_fees / nb, -3)

    month_labels = [m['label'] for m in months]

    return {
        'enrollment_months': month_labels,
        'enrollment_data': enrollment_data,
        'revenue_months': month_labels,
        'revenue_data': revenue_data,
        'objective': int(objective),
    }


def _compute_class_health(school, active_period):
    classes = list(
        school.classes.filter(is_active=True)
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
        .order_by('level', 'name')
    )
    if not classes:
        return []
    class_ids = [sc.id for sc in classes]

    # Taux de paiement — NOUVEAU modèle (lot 6bis-A) : dû ET versé calculés sur la MÊME
    # population (les fiches), via le helper central. Une classe sans aucune fiche →
    # dû=0 → taux « pas de données » (None), pas « 0% » trompeur (cf. plus bas).
    from apps.finance.services import fee_accounts_annotated
    accounts_by_class = (
        fee_accounts_annotated(school=school)
        .filter(enrollment__student__school_class__in=class_ids)
        .values('enrollment__student__school_class_id')
        .annotate(due_total=Sum('due'), paid_total=Sum('paid'))
    )
    fees_map = {r['enrollment__student__school_class_id']: r['due_total'] for r in accounts_by_class}
    paid_map = {r['enrollment__student__school_class_id']: r['paid_total'] for r in accounts_by_class}
    avg_map, total_bul_map, admitted_bul_map = {}, {}, {}
    if active_period:
        avg_map = {
            r['class_subject__school_class_id']: r['avg']
            for r in Note.objects.filter(
                class_subject__school_class__in=class_ids,
                period=active_period, is_cancelled=False,
            ).values('class_subject__school_class_id').annotate(avg=Avg('value'))
        }
        total_bul_map = {
            r['school_class_id']: r['count']
            for r in Bulletin.objects.filter(
                period=active_period, school_class__in=class_ids,
                is_cancelled=False, general_average__isnull=False,
            ).values('school_class_id').annotate(count=Count('id'))
        }
        admitted_bul_map = {
            r['school_class_id']: r['count']
            for r in Bulletin.objects.filter(
                period=active_period, school_class__in=class_ids,
                is_cancelled=False, general_average__gte=10,
            ).values('school_class_id').annotate(count=Count('id'))
        }

    rows = []
    for sc in classes:
        if sc.student_count == 0:
            continue
        class_avg = None
        raw_avg = avg_map.get(sc.id)
        if raw_avg:
            class_avg = round(float(raw_avg), 2)
        success_rate = None
        total = total_bul_map.get(sc.id, 0)
        if total > 0:
            admitted = admitted_bul_map.get(sc.id, 0)
            success_rate = round(admitted / total * 100, 1)
        total_fees = fees_map.get(sc.id) or 0
        total_paid = paid_map.get(sc.id) or 0
        # « pas de données » (None) si la classe n'a AUCUNE fiche, plutôt que « 0% » faux.
        has_fees = total_fees > 0
        payment_rate = round(total_paid / total_fees * 100, 1) if has_fees else None
        if has_fees:
            if class_avg and class_avg >= GOOD_AVERAGE_THRESHOLD and payment_rate > PAYMENT_GOOD_THRESHOLD:
                status = 'good'
            elif (class_avg and class_avg < PASS_THRESHOLD) or payment_rate < PAYMENT_CRITICAL_THRESHOLD:
                status = 'critical'
            else:
                status = 'warning'
        else:
            # Sans données de paiement → on ne classe que sur la moyenne (le paiement ne pénalise pas).
            if class_avg and class_avg < PASS_THRESHOLD:
                status = 'critical'
            elif class_avg and class_avg >= GOOD_AVERAGE_THRESHOLD:
                status = 'good'
            else:
                status = 'warning'
        rows.append({
            'class': sc, 'student_count': sc.student_count,
            'avg': class_avg, 'success_rate': success_rate,
            'payment_rate': payment_rate, 'status': status,
        })
    return rows


from datetime import datetime, time
from django.utils import timezone as tz

def _compute_activity(school):
    activity = []
    aware_tz = tz.get_current_timezone()
    for p in Payment.objects.filter(student__school=school, is_cancelled=False).select_related('student', 'collected_by').order_by('-payment_date')[:5]:
        activity.append({
            'type': 'payment', 'icon': 'credit-card',
            'label': 'Paiement enregistr\u00e9',
            'color': 'text-green-500 bg-green-50',
            'time': p.payment_date,
            'text': f'{p.student.full_name} -- {int(p.amount):,} FCFA ({p.get_payment_method_display()})',
            'url': reverse('payments:dashboard'),
        })
    for b in Bulletin.objects.filter(school_class__school=school, is_cancelled=False).select_related('student', 'school_class', 'period').order_by('-generated_at')[:5]:
        dt = b.generated_at
        activity.append({
            'type': 'bulletin', 'icon': 'file-text',
            'label': 'Bulletin g\u00e9n\u00e9r\u00e9',
            'color': 'text-blue-500 bg-blue-50',
            'time': dt,
            'text': f'{b.school_class.name} -- {b.period.name} -- {b.student.full_name}',
            'url': reverse('bulletins:main'),
        })
    for n in Note.objects.filter(class_subject__school_class__school=school).select_related('student', 'class_subject__subject', 'class_subject__school_class', 'entered_by').order_by('-entered_at')[:5]:
        activity.append({
            'type': 'note', 'icon': 'book-open',
            'label': 'Notes saisies',
            'color': 'text-amber-500 bg-amber-50',
            'time': n.entered_at,
            'text': f'{n.entered_by.full_name} -- {n.class_subject.subject.name} ({n.class_subject.school_class.name})',
            'url': f'/notes/{n.class_subject.school_class_id}/{n.period_id}/',
        })
    for s in Student.objects.filter(school=school, is_active=True).order_by('-enrolled_at')[:5]:
        activity.append({
            'type': 'student', 'icon': 'user-plus',
            'label': '\u00c9l\u00e8ve inscrit',
            'color': 'text-purple-500 bg-purple-50',
            'time': s.enrolled_at,
            'text': f'{s.full_name} -- {s.school_class.name if s.school_class else "Aucune classe"}',
            'url': reverse('students:list'),
        })
    # Normaliser date -> datetime aware, puis trier par timestamp
    def _sort_key(item):
        val = item['time']
        if isinstance(val, datetime) and tz.is_aware(val):
            return val
        if isinstance(val, datetime):
            return val.replace(tzinfo=aware_tz)
        return datetime(val.year, val.month, val.day, tzinfo=aware_tz)
    activity.sort(key=_sort_key, reverse=True)
    return activity[:10]
