"""Cockpit de classe — agrégats pédagogiques et financiers d'une classe.

Service isolé (sans logique HTTP, testable) consommé par schools.views.class_detail.

Sources :
  - Notes  : moyenne /20 normalisée (value × 20 / max_grade de la matière), hors annulées.
  - Émargement : l'app ne logue QUE les absences/retards (jamais les présents) →
    on compte les absences sur une fenêtre, on n'invente pas de « taux de présence ».
  - Finances : finance.services.fee_accounts_annotated (dû / payé / solde par fiche).
"""
from datetime import timedelta

from django.db.models import Avg, Count, F, FloatField, ExpressionWrapper
from django.utils import timezone

from apps.schools.models import Note
from apps.teachers.models import Attendance
from apps.students.models import Student
from apps.finance.services import fee_accounts_annotated

# Note ramenée sur 20, quel que soit le barème de la matière.
_NORM = ExpressionWrapper(F('value') * 20.0 / F('class_subject__max_grade'),
                          output_field=FloatField())

# Seuils « élève à risque » et fenêtre d'observation (ajustables).
RISK_AVG = 10          # moyenne /20 sous laquelle on alerte
RISK_ABSENCES = 3      # nb d'absences sur la fenêtre au-delà duquel on alerte
WINDOW_DAYS = 30


def build_class_cockpit(school, school_class, *, window_days=WINDOW_DAYS,
                        risk_avg=RISK_AVG, risk_absences=RISK_ABSENCES):
    """Renvoie un dict structuré : kpis, roster, at_risk, subjects_avg, class_subjects."""
    cutoff = timezone.localdate() - timedelta(days=window_days)
    notes = Note.objects.filter(class_subject__school_class=school_class, is_cancelled=False)
    window = Attendance.objects.filter(school_class=school_class, date__gte=cutoff)

    # ── Agrégats par élève (un .values() par métrique → pas de jointures qui se multiplient) ──
    moy_by_student = {r['student']: r['m'] for r in notes.values('student').annotate(m=Avg(_NORM))}
    abs_by_student = {r['student']: r['n'] for r in
                      window.filter(status='absent').values('student').annotate(n=Count('id'))}
    accounts = list(
        fee_accounts_annotated(school=school)
        .filter(enrollment__school_class=school_class)
        .select_related('enrollment')
    )
    bal_by_student = {a.enrollment.student_id: a.balance for a in accounts}

    # ── Roster (tous les élèves actifs ; données manquantes = None) ──
    students = Student.objects.filter(school_class=school_class, is_active=True).order_by('full_name')
    roster = []
    for s in students:
        moy = moy_by_student.get(s.id)
        absences = abs_by_student.get(s.id, 0)
        at_risk = (moy is not None and moy < risk_avg) or (absences >= risk_absences)
        roster.append({
            'student':  s,
            'moyenne':  round(moy, 1) if moy is not None else None,
            'absences': absences,
            'balance':  bal_by_student.get(s.id),
            'at_risk':  at_risk,
        })

    at_risk = sorted(
        (r for r in roster if r['at_risk']),
        key=lambda r: (r['moyenne'] if r['moyenne'] is not None else 99, -r['absences']),
    )

    # ── Moyenne par matière (vue d'ensemble) ──
    subjects_avg = [
        {'subject': r['class_subject__subject__name'], 'moyenne': round(r['m'], 1)}
        for r in notes.values('class_subject__subject__name').annotate(m=Avg(_NORM)).order_by('-m')
        if r['m'] is not None
    ]

    # ── Matières & enseignants (le « trou » comblé) ──
    class_subjects = (
        school_class.class_subjects.filter(is_active=True)
        .select_related('subject', 'teacher')
        .order_by('order', 'subject__name')
    )

    # ── KPIs ──
    moy_classe = notes.aggregate(m=Avg(_NORM))['m']
    due = sum(a.due for a in accounts)
    paid = sum(a.paid for a in accounts)
    kpis = {
        'effectif':     len(roster),
        'boys':         sum(1 for r in roster if r['student'].gender == 'M'),
        'girls':        sum(1 for r in roster if r['student'].gender == 'F'),
        'max_capacity': school_class.max_capacity,
        'moyenne':      round(moy_classe, 1) if moy_classe is not None else None,
        'absences':     window.filter(status='absent').count(),
        'retards':      window.filter(status='late').count(),
        'due':          due,
        'paid':         paid,
        'recouvrement': round(paid / due * 100) if due else None,
        'at_risk_count': len(at_risk),
        'window_days':  window_days,
    }

    return {
        'kpis':           kpis,
        'roster':         roster,
        'at_risk':        at_risk,
        'subjects_avg':   subjects_avg,
        'class_subjects': class_subjects,
    }
