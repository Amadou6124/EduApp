"""Services Comptabilité — calcul des heures, preview de paie, fiche PDF."""
from decimal import Decimal

from django.db.models import Sum

from apps.accounts.models import UserRole

# Dernier filet : durée d'une séance sans créneau EDT ni heures tapées. L'émargement
# invite à saisir la vraie durée ; cette valeur n'évite qu'un « 0 » silencieux.
DEFAULT_SESSION_HOURS = Decimal('2')


def _slot_hours_map(school, year, month):
    """{(class_subject_id, weekday): Decimal(heures)} = somme des créneaux EDT d'un
    cours ce jour-là, pour l'année scolaire qui couvre ce mois. Un mois calendaire
    tombe dans UNE seule année scolaire. Vide si aucune année ne couvre le mois.

    C'est la SOURCE des durées : peu importe la forme de la journée (continue jusqu'à
    15h, cours du soir…), le créneau porte ses vraies heures. Plus de « matin/après-midi »
    ni de ×2 : on additionne ce qui est réellement au planning ce jour."""
    import datetime
    from apps.schools.models import SchoolYear, CourseSlot
    mid = datetime.date(year, month, 15)
    sy = (SchoolYear.objects
          .filter(school=school, start_date__lte=mid, end_date__gte=mid)
          .order_by('-start_date').first())
    if sy is None:
        return {}
    mins = {}
    for cs_id, day, st, et in (
        CourseSlot.objects.filter(school_year=sy)
        .values_list('class_subject_id', 'day', 'start_time', 'end_time')
    ):
        d = (et.hour * 60 + et.minute) - (st.hour * 60 + st.minute)
        if d > 0:
            mins[(cs_id, day)] = mins.get((cs_id, day), 0) + d
    return {k: (Decimal(v) / Decimal('60')) for k, v in mins.items()}


def _effective_hours(row, slot_map):
    """Heures d'une séance émargée, dans l'ordre :
      1. heures RÉELLES tapées (« partiel » / cours hors EDT) ;
      2. somme des créneaux EDT du cours ce jour (la norme) ;
      3. dernier filet DEFAULT_SESSION_HOURS (aucun créneau, aucune saisie).
    `row` expose hours, class_subject_id, date."""
    if row['hours'] is not None:
        return row['hours']
    planned = slot_map.get((row['class_subject_id'], row['date'].weekday()))
    if planned is not None:
        return planned
    return DEFAULT_SESSION_HOURS


def compute_teacher_hours(school, year, month):
    """
    Heures de chaque user pour le mois. La durée d'une séance vient de l'EMPLOI DU
    TEMPS (somme des créneaux du jour) ; des heures tapées la remplacent (« partiel »).
    Cumule (titulaire 'present') + (remplaçant 'replaced'). {user_id: Decimal}.
    """
    from .models import TeacherAttendance
    slot_map = _slot_hours_map(school, year, month)
    hours = {}

    def _add(uid, h):
        hours[uid] = hours.get(uid, Decimal('0')) + h

    for r in (
        TeacherAttendance.objects
        .filter(school=school, date__year=year, date__month=month, status='present')
        .values('teacher_id', 'class_subject_id', 'hours', 'date')
    ):
        _add(r['teacher_id'], _effective_hours(r, slot_map))

    for r in (
        TeacherAttendance.objects
        .filter(school=school, date__year=year, date__month=month,
                status='replaced', substitute__isnull=False)
        .values('substitute_id', 'class_subject_id', 'hours', 'date')
    ):
        _add(r['substitute_id'], _effective_hours(r, slot_map))

    return hours


def compute_vacataire_pay(school, year, month):
    """Paie vacataire PAR COURS : Σ (heures émargées « présent » du cours × tarif).
    La durée vient de l'EDT (créneaux du jour) ; les heures tapées la remplacent.

    Le remplacement n'est PAS crédité ici : le remplaçant assure sa PROPRE matière
    (émargée à son nom). Retourne {user_id: {amount, hours, courses, unrated_hours}}.
    """
    from collections import defaultdict
    from .models import TeacherAttendance, VacataireRate, EmploymentType

    rate_map = {
        vr.class_subject_id: vr.hourly_rate
        for vr in VacataireRate.objects.filter(
            profile__membership__school=school,
            profile__employment_type=EmploymentType.VACATAIRE,
        )
    }
    slot_map = _slot_hours_map(school, year, month)
    acc = defaultdict(lambda: {'amount': Decimal('0'), 'hours': Decimal('0'),
                               'courses': set(), 'unrated_hours': Decimal('0')})
    rows = (
        TeacherAttendance.objects
        .filter(school=school, date__year=year, date__month=month, status='present')
        .values('teacher_id', 'class_subject_id', 'hours', 'date')
    )
    for r in rows:
        eff = _effective_hours(r, slot_map)
        d = acc[r['teacher_id']]
        d['hours'] += eff
        d['courses'].add(r['class_subject_id'])
        rate = rate_map.get(r['class_subject_id'])
        if rate is not None:
            d['amount'] += eff * rate
        else:
            d['unrated_hours'] += eff
    return {
        uid: {'amount': v['amount'], 'hours': v['hours'],
              'courses': len(v['courses']), 'unrated_hours': v['unrated_hours']}
        for uid, v in acc.items()
    }


def compute_permanent_deductions(school, year, month):
    """Retenue des permanents : nb de cours absents × school.absence_deduction.

    Retourne {user_id: {absences, deduction}}. Vide si absence_deduction = 0.
    """
    from django.db.models import Count
    from .models import TeacherAttendance, EmployeeProfile, EmploymentType

    per_abs = school.absence_deduction or Decimal('0')
    perm_ids = set(
        EmployeeProfile.objects.filter(
            membership__school=school, employment_type=EmploymentType.PERMANENT, is_active=True,
        ).values_list('membership__user_id', flat=True)
    )
    if not perm_ids:
        return {}
    rows = (
        TeacherAttendance.objects
        .filter(school=school, date__year=year, date__month=month,
                status='absent', teacher_id__in=perm_ids)
        .values('teacher_id').annotate(n=Count('id'))
    )
    return {
        r['teacher_id']: {'absences': r['n'], 'deduction': per_abs * r['n']}
        for r in rows
    }


def _row(membership, profile, vac_map, ded_map, existing):
    """Construit une ligne de paie (commun preview + re-render après action)."""
    from .models import EmploymentType

    if profile is None or not profile.is_active:
        return {
            'membership': membership, 'profile': profile,
            'computed_hours': None, 'computed_amount': Decimal('0'),
            'courses': 0, 'unrated_hours': Decimal('0'),
            'gross': Decimal('0'), 'deduction': Decimal('0'), 'absences': 0,
            'existing_payment': existing, 'status': 'not_configured',
        }
    if profile.employment_type == EmploymentType.PERMANENT:
        gross = profile.monthly_salary or Decimal('0')
        d = ded_map.get(membership.user_id) or {}
        deduction = d.get('deduction', Decimal('0'))
        absences = d.get('absences', 0)
        amount = gross - deduction
        if amount < 0:
            amount = Decimal('0')
        hrs, courses, unrated = None, 0, Decimal('0')
    else:
        v = vac_map.get(membership.user_id) or {}
        hrs = v.get('hours', Decimal('0'))
        amount = v.get('amount', Decimal('0'))
        courses = v.get('courses', 0)
        unrated = v.get('unrated_hours', Decimal('0'))
        gross, deduction, absences = amount, Decimal('0'), 0
    return {
        'membership': membership, 'profile': profile,
        'computed_hours': hrs, 'computed_amount': amount,
        'courses': courses, 'unrated_hours': unrated,
        'gross': gross, 'deduction': deduction, 'absences': absences,
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
        .exclude(role__in=[UserRole.PARENT, UserRole.STUDENT])
        .select_related('user', 'employee_profile')
        .order_by('user__full_name')
    )
    vac_map = compute_vacataire_pay(school, year, month)
    ded_map = compute_permanent_deductions(school, year, month)
    pay_map = {
        p.employee_id: p
        for p in SalaryPayment.objects.filter(
            school=school, year=year, month=month, is_cancelled=False,
        )
    }

    permanents, vacataires, not_configured = [], [], []
    for m in memberships:
        profile = getattr(m, 'employee_profile', None)
        row = _row(m, profile, vac_map, ded_map, pay_map.get(m.id))
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
    vac_map = compute_vacataire_pay(school, year, month)
    ded_map = compute_permanent_deductions(school, year, month)
    existing = SalaryPayment.objects.filter(
        employee=membership, year=year, month=month, is_cancelled=False,
    ).first()
    return _row(membership, profile, vac_map, ded_map, existing)


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
        'gross': (payment.amount or Decimal('0')) + (payment.deduction or Decimal('0')),
    })
    return HTML(string=html).write_pdf()
