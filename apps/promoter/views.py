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
from django.shortcuts import get_object_or_404, render
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


@login_required
@promoter_required
def promoter_school_detail(request, school_id):
    """Vue lecture seule d'une école du groupe du promoteur. 6 requêtes, zéro N+1."""
    from apps.schools.models import School, SchoolClass, ClassSubject
    from apps.students.models import Student
    from apps.payments.models import Payment
    from apps.teachers.models import Attendance, AttendanceStatus

    # 0. Sécurité : le promoteur ne voit QUE les écoles de son groupe
    school = get_object_or_404(
        School.objects.select_related('group'),
        pk=school_id, group__owner=request.user, is_active=True,
    )
    now = timezone.now()
    today = now.date()

    # 1. Classes : effectif + dû par classe (étudiants actifs) — pas de jointure paiements (fan-out)
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

    # 2. Paiements par (classe, mois) — un seul scan → payé/classe + payé/mois
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

    # 3. ClassSubject : équipe + prof principal + comptage profs (1 requête, select_related)
    cs_rows = list(
        ClassSubject.objects.filter(school_class__school=school, is_active=True)
        .select_related('teacher', 'subject', 'school_class')
        .order_by('order', 'subject__name')
    )
    # Prof principal = teacher du ClassSubject de plus petit order (puis subject.name)
    principal = {}
    for cs in cs_rows:
        if cs.school_class_id not in principal:
            principal[cs.school_class_id] = cs.teacher

    # Équipe : teacher_id → matières + classes
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

    # Fusion par classe
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

    # 4. Alerte impayés > 30 jours : balance > 0 ET enrolled_at < today - 30j
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

    # 5. Alerte absences ce mois
    absences_month = Attendance.objects.filter(
        school=school, status=AttendanceStatus.ABSENT,
        date__year=now.year, date__month=now.month,
    ).count()

    # Graphique 6 derniers mois
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
