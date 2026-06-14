"""Services Comptabilité — calcul des heures, preview de paie, fiche PDF."""
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, When


def compute_teacher_hours(school, year, month):
    """
    Heures de chaque user pour le mois. FULL_DAY = 2× duration_hours.
    Cumule (titulaire 'present') + (remplaçant 'replaced').
    Retourne {user_id: Decimal(heures)}. 2 requêtes GROUP BY → zéro N+1.
    """
    from .models import TeacherAttendance

    weighted = Case(
        When(session='full', then=F('class_subject__duration_hours') * 2),
        default=F('class_subject__duration_hours'),
        output_field=DecimalField(max_digits=8, decimal_places=1),
    )
    hours = {}

    for row in (
        TeacherAttendance.objects
        .filter(school=school, date__year=year, date__month=month, status='present')
        .values('teacher_id').annotate(h=Sum(weighted))
    ):
        hours[row['teacher_id']] = hours.get(row['teacher_id'], Decimal('0')) + (row['h'] or Decimal('0'))

    for row in (
        TeacherAttendance.objects
        .filter(school=school, date__year=year, date__month=month,
                status='replaced', substitute__isnull=False)
        .values('substitute_id').annotate(h=Sum(weighted))
    ):
        hours[row['substitute_id']] = hours.get(row['substitute_id'], Decimal('0')) + (row['h'] or Decimal('0'))

    return hours


def _row(membership, profile, hours_map, existing):
    """Construit une ligne de paie (commun preview + re-render après action)."""
    from .models import EmploymentType

    if profile is None or not profile.is_active:
        return {
            'membership': membership, 'profile': profile,
            'computed_hours': None, 'computed_amount': Decimal('0'),
            'existing_payment': existing, 'status': 'not_configured',
        }
    if profile.employment_type == EmploymentType.PERMANENT:
        amount, hrs = (profile.monthly_salary or Decimal('0')), None
    else:
        hrs = hours_map.get(membership.user_id, Decimal('0'))
        amount = hrs * (profile.hourly_rate or Decimal('0'))
    return {
        'membership': membership, 'profile': profile,
        'computed_hours': hrs, 'computed_amount': amount,
        'existing_payment': existing,
        'status': existing.status if existing else 'unpaid',
    }


def compute_monthly_salary_preview(school, year, month):
    """
    Preview de la paie d'un mois, groupé par employment_type. Zéro N+1 (~4 requêtes).
    """
    from apps.accounts.models import Membership
    from .models import SalaryPayment, EmploymentType

    memberships = (
        Membership.objects
        .filter(school=school, is_active=True)
        .exclude(role__in=['parent', 'student'])
        .select_related('user', 'employee_profile')
        .order_by('user__full_name')
    )
    hours_map = compute_teacher_hours(school, year, month)
    pay_map = {
        p.employee_id: p
        for p in SalaryPayment.objects.filter(
            school=school, year=year, month=month, is_cancelled=False,
        )
    }

    permanents, vacataires, not_configured = [], [], []
    for m in memberships:
        profile = getattr(m, 'employee_profile', None)
        row = _row(m, profile, hours_map, pay_map.get(m.id))
        if row['status'] == 'not_configured':
            not_configured.append(row)
        elif profile.employment_type == EmploymentType.PERMANENT:
            permanents.append(row)
        else:
            vacataires.append(row)

    rows = permanents + vacataires
    totals = {
        'estimated': sum((r['computed_amount'] for r in rows), Decimal('0')),
        'paid': sum((r['existing_payment'].amount for r in rows
                     if r['existing_payment'] and r['existing_payment'].status == 'paid'), Decimal('0')),
        'pending': sum((r['existing_payment'].amount for r in rows
                        if r['existing_payment'] and r['existing_payment'].status == 'pending'), Decimal('0')),
    }
    return {
        'permanents': permanents, 'vacataires': vacataires,
        'not_configured': not_configured, 'totals': totals,
    }


def salary_row(school, membership, year, month):
    """Re-calcule une seule ligne (après pay/confirm/cancel)."""
    from .models import SalaryPayment

    profile = getattr(membership, 'employee_profile', None)
    hours_map = compute_teacher_hours(school, year, month)
    existing = SalaryPayment.objects.filter(
        employee=membership, year=year, month=month, is_cancelled=False,
    ).first()
    return _row(membership, profile, hours_map, existing)


def compute_monthly_balance(school, year, month):
    """
    Bilan financier d'un mois : revenus (paiements élèves) − charges (salaires payés + dépenses).
    ~4 requêtes agrégées, zéro N+1.
    """
    from django.db.models import Sum
    from apps.payments.models import Payment
    from .models import SalaryPayment, SalaryStatus, Expense

    revenus = Payment.objects.filter(
        student__school=school, is_cancelled=False,
        payment_date__year=year, payment_date__month=month,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    salaires = SalaryPayment.objects.filter(
        school=school, year=year, month=month,
        status=SalaryStatus.PAID, is_cancelled=False,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    depenses = Expense.objects.filter(
        school=school, date__year=year, date__month=month, is_cancelled=False,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    by_cat = list(
        Expense.objects.filter(
            school=school, date__year=year, date__month=month, is_cancelled=False,
        ).values('category__name', 'category__icon').annotate(total=Sum('amount')).order_by('-total')
    )
    if depenses:
        for c in by_cat:
            c['pct'] = int(c['total'] / depenses * 100)

    charges = salaires + depenses
    return {
        'revenus': revenus, 'salaires': salaires, 'depenses': depenses,
        'charges': charges, 'resultat': revenus - charges,
        'by_cat': by_cat, 'year': year, 'month': month,
    }


def compute_balance_series(school, ref_year, ref_month, n=6):
    """Série des n derniers mois pour le graphique. 3 requêtes groupées (floats pour Chart.js)."""
    from datetime import date as _date
    from django.db.models import Q, Sum
    from django.db.models.functions import TruncMonth
    from apps.payments.models import Payment
    from .models import SalaryPayment, SalaryStatus, Expense

    months = []
    y, m = ref_year, ref_month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()
    start = _date(months[0][0], months[0][1], 1)

    rev = {(r['mo'].year, r['mo'].month): r['s'] for r in
           Payment.objects.filter(student__school=school, is_cancelled=False, payment_date__gte=start)
           .annotate(mo=TruncMonth('payment_date')).values('mo').annotate(s=Sum('amount'))}
    dep = {(r['mo'].year, r['mo'].month): r['s'] for r in
           Expense.objects.filter(school=school, is_cancelled=False, date__gte=start)
           .annotate(mo=TruncMonth('date')).values('mo').annotate(s=Sum('amount'))}
    qmonths = Q()
    for (yy, mm) in months:
        qmonths |= Q(year=yy, month=mm)
    sal = {(r['year'], r['month']): r['s'] for r in
           SalaryPayment.objects.filter(school=school, status=SalaryStatus.PAID, is_cancelled=False)
           .filter(qmonths).values('year', 'month').annotate(s=Sum('amount'))}

    series = []
    for (yy, mm) in months:
        r = float(rev.get((yy, mm), 0) or 0)
        ch = float((sal.get((yy, mm), 0) or 0) + (dep.get((yy, mm), 0) or 0))
        series.append({'year': yy, 'month': mm, 'revenus': r, 'charges': ch, 'resultat': r - ch})
    return series


def generate_payslip_pdf(payment):
    """Fiche de paie PDF (WeasyPrint) à partir des snapshots immuables de SalaryPayment."""
    from django.template.loader import render_to_string
    from weasyprint import HTML

    html = render_to_string('accounting/pdf/payslip.html', {
        'p': payment,
        'school': payment.school,
    })
    return HTML(string=html).write_pdf()
