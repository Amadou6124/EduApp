"""
Vues Promoteur — supervision multi-écoles (cross-école, lecture seule).
Le dashboard consolidé agrège sur owned_groups → schools.
Ne PAS utiliser get_school() ici : un promoteur peut n'avoir aucune école active.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth

from apps.accounts.models import UserRole
from apps.core.constants import PAYMENT_GOOD_THRESHOLD, PAYMENT_ALERT_THRESHOLD
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.mixins import promoter_required

_MOIS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
         'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']


def _status(taux):
    if taux >= PAYMENT_GOOD_THRESHOLD:
        return 'green'
    if taux >= PAYMENT_ALERT_THRESHOLD:
        return 'yellow'
    return 'red'


def _months_seq(n, now=None):
    """Retourne n (year, month) consécutifs, du plus ancien au plus récent."""
    if now is None:
        now = timezone.now()
    y, m = now.year, now.month
    seq = []
    for _ in range(n):
        seq.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    seq.reverse()
    return seq


# ── Vue 1 : Synthèse (remplace promoter_dashboard) ───────────────────────────

@login_required
@promoter_required
def promoter_synthese(request):
    """Dashboard consolidé : KPIs groupe + alertes + classement écoles + graphique 6 mois."""
    from apps.schools.models import SchoolGroup, SchoolClass
    from apps.students.models import Student
    from apps.payments.models import Payment

    group = (
        SchoolGroup.objects.filter(owner=request.user)
        .prefetch_related('schools')
        .first()
    )
    if group is None:
        return render(request, 'promoter/synthese.html', {'group': None})

    schools = [s for s in group.schools.all() if s.is_active]
    school_ids = [s.id for s in schools]
    now = timezone.now()

    due_map = {
        r['school_id']: r
        for r in Student.objects
        .filter(school_id__in=school_ids, is_active=True)
        .values('school_id')
        .annotate(total_due=Sum('tuition_fee'), student_count=Count('id'))
    }
    classes_map = {
        r['school_id']: r['n']
        for r in SchoolClass.objects
        .filter(school_id__in=school_ids, is_active=True)
        .values('school_id').annotate(n=Count('id'))
    }
    paid_map = {
        r['student__school_id']: r
        for r in Payment.objects
        .filter(student__school_id__in=school_ids, is_cancelled=False)
        .values('student__school_id')
        .annotate(total_paid=Sum('amount'), payers=Count('student_id', distinct=True))
    }
    month_map = {
        r['student__school_id']: r['paid_this_month']
        for r in Payment.objects
        .filter(
            student__school_id__in=school_ids, is_cancelled=False,
            payment_date__year=now.year, payment_date__month=now.month,
        )
        .values('student__school_id').annotate(paid_this_month=Sum('amount'))
    }

    schools_data = []
    for s in schools:
        due_row = due_map.get(s.id, {})
        total_due = due_row.get('total_due') or Decimal('0')
        student_count = due_row.get('student_count') or 0
        paid_row = paid_map.get(s.id, {})
        total_paid = paid_row.get('total_paid') or Decimal('0')
        payers = paid_row.get('payers') or 0
        taux = int(total_paid / total_due * 100) if total_due else 0
        schools_data.append({
            'school':          s,
            'student_count':   student_count,
            'class_count':     classes_map.get(s.id, 0),
            'total_due':       total_due,
            'total_paid':      total_paid,
            'unpaid':          max(total_due - total_paid, Decimal('0')),
            'unpaid_count':    max(student_count - payers, 0),
            'paid_this_month': month_map.get(s.id, 0) or 0,
            'taux':            taux,
            'status':          _status(taux),
        })

    schools_data.sort(key=lambda d: d['taux'])

    total_due_group  = sum(d['total_due'] for d in schools_data)
    total_paid_group = sum(d['total_paid'] for d in schools_data)
    taux_group = int(total_paid_group / total_due_group * 100) if total_due_group else 0
    alerts = [d for d in schools_data if d['status'] == 'red']

    seq = _months_seq(6, now)
    trunc = {
        (r['month'].year, r['month'].month): float(r['s'] or 0)
        for r in Payment.objects
        .filter(student__school_id__in=school_ids, is_cancelled=False)
        .annotate(month=TruncMonth('payment_date'))
        .values('month').annotate(s=Sum('amount'))
    }
    chart_labels = [_MOIS[mm - 1] for (yy, mm) in seq]
    chart_values = [trunc.get((yy, mm), 0) for (yy, mm) in seq]

    return render(request, 'promoter/synthese.html', {
        'group':            group,
        'schools_data':     schools_data,
        'total_schools':    len(schools_data),
        'total_students':   sum(d['student_count'] for d in schools_data),
        'total_due_group':  total_due_group,
        'total_paid_group': total_paid_group,
        'total_paid_month': sum(d['paid_this_month'] for d in schools_data),
        'taux_group':       taux_group,
        'alerts':           alerts,
        'now':              now,
        'chart_labels':     chart_labels,
        'chart_values':     chart_values,
    })


# ── Vue 2 : Écoles (vue comparative toutes écoles) ───────────────────────────

@login_required
@promoter_required
def promoter_ecoles(request):
    """Vue comparative : toutes les écoles du groupe avec métriques détaillées."""
    from apps.schools.models import SchoolGroup, SchoolClass
    from apps.students.models import Student
    from apps.payments.models import Payment
    from apps.accounts.models import Membership
    from apps.teachers.models import Attendance, AttendanceStatus

    now = timezone.now()

    group = (
        SchoolGroup.objects.filter(owner=request.user)
        .prefetch_related('schools')
        .first()
    )
    if group is None:
        return render(request, 'promoter/ecoles.html', {'group': None})

    schools = [s for s in group.schools.all() if s.is_active]
    school_ids = [s.id for s in schools]

    due_map = {
        r['school_id']: r
        for r in Student.objects
        .filter(school_id__in=school_ids, is_active=True)
        .values('school_id')
        .annotate(total_due=Sum('tuition_fee'), student_count=Count('id'))
    }
    paid_map = {
        r['student__school_id']: r['s']
        for r in Payment.objects
        .filter(student__school_id__in=school_ids, is_cancelled=False)
        .values('student__school_id').annotate(s=Sum('amount'))
    }
    class_map = {
        r['school_id']: r['n']
        for r in SchoolClass.objects
        .filter(school_id__in=school_ids, is_active=True)
        .values('school_id').annotate(n=Count('id'))
    }
    teacher_map = {
        r['school_id']: r['n']
        for r in Membership.objects
        .filter(school_id__in=school_ids, role=UserRole.TEACHER, is_active=True)
        .values('school_id').annotate(n=Count('id'))
    }
    abs_map = {
        r['school_id']: r['n']
        for r in Attendance.objects
        .filter(
            school_id__in=school_ids,
            status=AttendanceStatus.ABSENT,
            date__year=now.year,
            date__month=now.month,
        )
        .values('school_id').annotate(n=Count('id'))
    }

    # Impayés > 30 jours — un seul GROUP BY school (pas de boucle N+1)
    paid_sq = (
        Payment.objects
        .filter(student=OuterRef('pk'), is_cancelled=False)
        .values('student').annotate(s=Sum('amount')).values('s')
    )
    unpaid_rows = (
        Student.objects
        .filter(
            school_id__in=school_ids,
            is_active=True,
            enrolled_at__date__lte=now.date() - datetime.timedelta(days=30),
        )
        .annotate(paid=Coalesce(Subquery(paid_sq), Decimal('0'), output_field=DecimalField()))
        .filter(paid__lt=F('tuition_fee'))
        .values('school_id').annotate(n=Count('id'))
    )
    unpaid_map = {r['school_id']: r['n'] for r in unpaid_rows}

    schools_data = []
    for s in schools:
        due_row = due_map.get(s.id, {})
        total_due = due_row.get('total_due') or Decimal('0')
        student_count = due_row.get('student_count') or 0
        total_paid = paid_map.get(s.id) or Decimal('0')
        taux = int(total_paid / total_due * 100) if total_due else 0
        schools_data.append({
            'school':         s,
            'student_count':  student_count,
            'class_count':    class_map.get(s.id, 0),
            'teacher_count':  teacher_map.get(s.id, 0),
            'total_due':      total_due,
            'total_paid':     total_paid,
            'unpaid':         max(total_due - total_paid, Decimal('0')),
            'unpaid_30':      unpaid_map.get(s.id, 0),
            'absences_month': abs_map.get(s.id, 0),
            'taux':           taux,
            'status':         _status(taux),
        })

    schools_data.sort(key=lambda d: d['taux'])

    return render(request, 'promoter/ecoles.html', {
        'group':        group,
        'schools_data': schools_data,
    })


# ── Vue 3 : Finances (P&L mensuelle) ─────────────────────────────────────────

@login_required
@promoter_required
def promoter_finances(request):
    """Vue P&L mensuelle : revenus (paiements), charges (salaires + dépenses), résultat net."""
    from apps.schools.models import SchoolGroup
    from apps.payments.models import Payment
    from apps.accounting.models import SalaryPayment, Expense

    now = timezone.now()

    # Parse ?month=YYYY-MM (défaut : mois courant)
    month_str = request.GET.get('month', '')
    try:
        year  = int(month_str[:4])
        month = int(month_str[5:7])
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, TypeError, IndexError):
        year, month = now.year, now.month

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1
    is_future  = (year, month) > (now.year, now.month)

    group = (
        SchoolGroup.objects.filter(owner=request.user)
        .prefetch_related('schools')
        .first()
    )
    if group is None:
        return render(request, 'promoter/finances.html', {'group': None})

    schools    = [s for s in group.schools.all() if s.is_active]
    school_ids = [s.id for s in schools]
    acc_ids    = [s.id for s in schools if s.accounting_enabled]

    pay_map = {
        r['student__school_id']: r['s']
        for r in Payment.objects
        .filter(
            student__school_id__in=school_ids, is_cancelled=False,
            payment_date__year=year, payment_date__month=month,
        )
        .values('student__school_id').annotate(s=Sum('amount'))
    }
    sal_map = (
        {
            r['school_id']: r['s']
            for r in SalaryPayment.objects
            .filter(
                school_id__in=acc_ids, is_cancelled=False,
                status='paid', year=year, month=month,
            )
            .values('school_id').annotate(s=Sum('amount'))
        }
        if acc_ids else {}
    )
    exp_map = (
        {
            r['school_id']: r['s']
            for r in Expense.objects
            .filter(
                school_id__in=acc_ids, is_cancelled=False,
                date__year=year, date__month=month,
            )
            .values('school_id').annotate(s=Sum('amount'))
        }
        if acc_ids else {}
    )

    schools_data = []
    for s in schools:
        revenus  = pay_map.get(s.id) or Decimal('0')
        salaires = (sal_map.get(s.id) or Decimal('0')) if s.accounting_enabled else Decimal('0')
        depenses = (exp_map.get(s.id) or Decimal('0')) if s.accounting_enabled else Decimal('0')
        charges  = salaires + depenses
        net      = revenus - charges
        schools_data.append({
            'school':   s,
            'revenus':  revenus,
            'salaires': salaires,
            'depenses': depenses,
            'charges':  charges,
            'net':      net,
        })

    total_revenus = sum(d['revenus'] for d in schools_data)
    total_charges = sum(d['charges'] for d in schools_data)
    total_net     = total_revenus - total_charges

    # Graphique 12 mois
    seq12 = _months_seq(12, now)

    pay_12 = {
        (r['month'].year, r['month'].month): float(r['s'] or 0)
        for r in Payment.objects
        .filter(student__school_id__in=school_ids, is_cancelled=False)
        .annotate(month=TruncMonth('payment_date'))
        .values('month').annotate(s=Sum('amount'))
    }
    sal_12 = (
        {
            (r['year'], r['month']): float(r['s'] or 0)
            for r in SalaryPayment.objects
            .filter(school_id__in=acc_ids, is_cancelled=False, status='paid')
            .values('year', 'month').annotate(s=Sum('amount'))
        }
        if acc_ids else {}
    )
    exp_12 = (
        {
            (r['month'].year, r['month'].month): float(r['s'] or 0)
            for r in Expense.objects
            .filter(school_id__in=acc_ids, is_cancelled=False)
            .annotate(month=TruncMonth('date'))
            .values('month').annotate(s=Sum('amount'))
        }
        if acc_ids else {}
    )

    chart_labels  = [_MOIS[mm - 1] for (yy, mm) in seq12]
    chart_revenus = [pay_12.get((yy, mm), 0) for (yy, mm) in seq12]
    chart_charges = [sal_12.get((yy, mm), 0) + exp_12.get((yy, mm), 0) for (yy, mm) in seq12]

    return render(request, 'promoter/finances.html', {
        'group':         group,
        'schools_data':  schools_data,
        'year':          year,
        'month':         month,
        'month_label':   _MOIS[month - 1],
        'prev_year':     prev_year,
        'prev_month':    prev_month,
        'next_year':     next_year,
        'next_month':    next_month,
        'is_future':     is_future,
        'total_revenus': total_revenus,
        'total_charges': total_charges,
        'total_net':     total_net,
        'now':           now,
        'chart_labels':  chart_labels,
        'chart_revenus': chart_revenus,
        'chart_charges': chart_charges,
    })


# ── Vue 4 : Détail école (inchangée) ─────────────────────────────────────────

@login_required
@promoter_required
def promoter_school_detail(request, school_id):
    """Vue lecture seule d'une école du groupe du promoteur. 6 requêtes, zéro N+1."""
    from apps.schools.models import School, SchoolClass, ClassSubject
    from apps.students.models import Student
    from apps.payments.models import Payment
    from apps.teachers.models import Attendance, AttendanceStatus

    school = get_object_or_404(
        School.objects.select_related('group'),
        pk=school_id, group__owner=request.user, is_active=True,
    )
    now = timezone.now()
    today = now.date()

    classes = list(
        SchoolClass.objects.filter(school=school, is_active=True)
        .annotate(
            n_students=Count('students', filter=Q(students__is_active=True)),
            due=Coalesce(
                Sum('students__tuition_fee', filter=Q(students__is_active=True)),
                Decimal('0'),
            ),
        )
        .order_by('level', 'name')
    )

    pay_rows = (
        Payment.objects.filter(student__school=school, is_cancelled=False)
        .annotate(month=TruncMonth('payment_date'))
        .values('student__school_class_id', 'month')
        .annotate(p=Sum('amount'))
    )
    paid_by_class = defaultdict(lambda: Decimal('0'))
    paid_by_month = defaultdict(float)
    for r in pay_rows:
        amt = r['p'] or Decimal('0')
        paid_by_class[r['student__school_class_id']] += amt
        if r['month']:
            paid_by_month[(r['month'].year, r['month'].month)] += float(amt)

    cs_rows = list(
        ClassSubject.objects.filter(school_class__school=school, is_active=True)
        .select_related('teacher', 'subject', 'school_class')
        .order_by('order', 'subject__name')
    )
    principal = {}
    for cs in cs_rows:
        if cs.school_class_id not in principal:
            principal[cs.school_class_id] = cs.teacher

    tmap = {}
    for cs in cs_rows:
        if cs.teacher_id is None:
            continue
        entry = tmap.setdefault(cs.teacher_id, {'teacher': cs.teacher, 'subjects': [], 'classes': set()})
        if cs.subject.name not in entry['subjects']:
            entry['subjects'].append(cs.subject.name)
        entry['classes'].add(cs.school_class_id)
    teachers_data = sorted(
        ({'teacher': v['teacher'], 'subjects': v['subjects'], 'class_count': len(v['classes'])}
         for v in tmap.values()),
        key=lambda d: d['teacher'].full_name,
    )

    classes_data = []
    total_students = 0
    total_due = Decimal('0')
    for c in classes:
        due = c.due or Decimal('0')
        paid = paid_by_class.get(c.id, Decimal('0'))
        taux = int(paid / due * 100) if due else 0
        classes_data.append({
            'cls': c, 'n_students': c.n_students, 'due': due, 'paid': paid,
            'taux': taux, 'status': _status(taux), 'principal': principal.get(c.id),
        })
        total_students += c.n_students
        total_due += due
    total_paid = sum(paid_by_class.values(), Decimal('0'))
    taux_global = int(total_paid / total_due * 100) if total_due else 0

    paid_sq = (
        Payment.objects.filter(student=OuterRef('pk'), is_cancelled=False)
        .values('student').annotate(s=Sum('amount')).values('s')
    )
    unpaid_30 = (
        Student.objects
        .filter(
            school=school, is_active=True,
            enrolled_at__date__lte=today - datetime.timedelta(days=30),
        )
        .annotate(paid=Coalesce(Subquery(paid_sq), Decimal('0'), output_field=DecimalField()))
        .filter(paid__lt=F('tuition_fee'))
        .count()
    )

    absences_month = Attendance.objects.filter(
        school=school, status=AttendanceStatus.ABSENT,
        date__year=now.year, date__month=now.month,
    ).count()

    y, m = now.year, now.month
    months_seq = []
    for _ in range(6):
        months_seq.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months_seq.reverse()
    chart_labels = [_MOIS[mm - 1] for (yy, mm) in months_seq]
    chart_values = [paid_by_month.get((yy, mm), 0) for (yy, mm) in months_seq]

    return render(request, 'promoter/school_detail.html', {
        'group':          school.group,
        'school':         school,
        'status':         _status(taux_global),
        'total_students': total_students,
        'total_teachers': len(teachers_data),
        'total_classes':  len(classes_data),
        'total_due':      total_due,
        'total_paid':     total_paid,
        'taux_global':    taux_global,
        'classes_data':   classes_data,
        'teachers_data':  teachers_data,
        'unpaid_30':      unpaid_30,
        'absences_month': absences_month,
        'chart_labels':   chart_labels,
        'chart_values':   chart_values,
    })
