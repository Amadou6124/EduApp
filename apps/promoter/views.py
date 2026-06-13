"""
Vues Promoteur — supervision multi-écoles (cross-école, lecture seule).
Le dashboard consolidé agrège sur owned_groups → schools.
Ne PAS utiliser get_school() ici : un promoteur peut n'avoir aucune école active.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from apps.core.mixins import promoter_required

_MOIS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
         'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']


def _status(taux):
    if taux >= 80:
        return 'green'
    if taux >= 60:
        return 'yellow'
    return 'red'


@login_required
@promoter_required
def promoter_dashboard(request):
    from apps.schools.models import SchoolGroup, SchoolClass
    from apps.students.models import Student
    from apps.payments.models import Payment
    from apps.accounts.models import Membership

    group = (
        SchoolGroup.objects.filter(owner=request.user)
        .prefetch_related('schools')
        .first()
    )
    if group is None:
        return render(request, 'promoter/dashboard.html', {'group': None})

    schools = [s for s in group.schools.all() if s.is_active]
    school_ids = [s.id for s in schools]
    now = timezone.now()

    # ── Agrégats : 4 requêtes GROUP BY, indépendantes du nombre d'écoles ──
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
    membership_ids = set(
        Membership.objects
        .filter(user=request.user, school_id__in=school_ids, is_active=True)
        .values_list('school_id', flat=True)
    )

    # ── Fusion en mémoire ────────────────────────────────────────────────
    schools_data = []
    for s in schools:
        due_row = due_map.get(s.id, {})
        total_due = due_row.get('total_due') or 0
        student_count = due_row.get('student_count') or 0
        paid_row = paid_map.get(s.id, {})
        total_paid = paid_row.get('total_paid') or 0
        payers = paid_row.get('payers') or 0
        taux = int(total_paid / total_due * 100) if total_due else 0
        schools_data.append({
            'school':          s,
            'student_count':   student_count,
            'class_count':     classes_map.get(s.id, 0),
            'total_due':       total_due,
            'total_paid':      total_paid,
            'unpaid':          max(total_due - total_paid, 0),
            'unpaid_count':    max(student_count - payers, 0),
            'paid_this_month': month_map.get(s.id, 0) or 0,
            'taux':            taux,
            'status':          _status(taux),
            'has_membership':  s.id in membership_ids,
        })

    schools_data.sort(key=lambda d: d['taux'])  # pire recouvrement en premier

    # ── Totaux groupe ────────────────────────────────────────────────────
    total_due_group  = sum(d['total_due'] for d in schools_data)
    total_paid_group = sum(d['total_paid'] for d in schools_data)
    taux_group = int(total_paid_group / total_due_group * 100) if total_due_group else 0
    alerts = [d for d in schools_data if d['status'] == 'red']

    # ── Évolution paiements 6 derniers mois (données réelles) ────────────
    y, m = now.year, now.month
    months_seq = []
    for _ in range(6):
        months_seq.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months_seq.reverse()

    trunc = {
        (r['month'].year, r['month'].month): float(r['s'] or 0)
        for r in Payment.objects
        .filter(student__school_id__in=school_ids, is_cancelled=False)
        .annotate(month=TruncMonth('payment_date'))
        .values('month').annotate(s=Sum('amount'))
    }
    chart_labels = [_MOIS[mm - 1] for (yy, mm) in months_seq]
    chart_values = [trunc.get((yy, mm), 0) for (yy, mm) in months_seq]

    return render(request, 'promoter/dashboard.html', {
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
