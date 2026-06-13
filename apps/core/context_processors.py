import datetime
from decimal import Decimal

from django.db.models import (
    Count, F, OuterRef, Q, Subquery, Sum, DecimalField
)
from django.db.models.functions import Coalesce


def school_context(request):
    """
    Injecte dans chaque template :
      - active_year  : SchoolYear active (avec .period_name annoté)
      - alert_count  : nb d'élèves avec solde > 0 (impayés + partiels)

    Performance : 2 requêtes SQL par page authentifiée avec école.
      Req 1 — SchoolYear (LIMIT 1) + prefetch Period → 2 SQL internes, 1 unité logique
      Req 2 — COUNT avec subquery corréléé sur Student/Payment
    """
    if not request.user.is_authenticated:
        return {}

    school = getattr(request, 'school', None)
    if not school:
        return {}

    from apps.schools.models import SchoolYear, Period
    from apps.students.models import Student
    from apps.payments.models import Payment

    today = datetime.date.today()

    # ── Requête 1 : année scolaire active + période courante ──────────────────
    # La période courante est la première dont la plage de dates couvre aujourd'hui.
    # Si aucune ne couvre today, on prend la première par ordre.
    current_period_sq = (
        Period.objects
        .filter(
            school_year=OuterRef('pk'),
            start_date__lte=today,
            end_date__gte=today,
        )
        .order_by('order')
        .values('name')[:1]
    )
    fallback_period_sq = (
        Period.objects
        .filter(school_year=OuterRef('pk'))
        .order_by('order')
        .values('name')[:1]
    )

    active_year = (
        SchoolYear.objects
        .filter(school=school, is_active=True)
        .annotate(
            period_name=Coalesce(
                Subquery(current_period_sq),
                Subquery(fallback_period_sq),
            )
        )
        .first()
    )

    # ── Requête 2 : élèves avec solde restant > 0 ─────────────────────────────
    paid_sq = (
        Payment.objects
        .filter(student=OuterRef('pk'), is_cancelled=False)
        .values('student')
        .annotate(s=Sum('amount'))
        .values('s')
    )
    alert_count = (
        Student.objects
        .filter(school=school, is_active=True)
        .annotate(
            valid_paid=Coalesce(
                Subquery(paid_sq), Decimal('0'), output_field=DecimalField()
            )
        )
        .filter(valid_paid__lt=F('tuition_fee'))
        .count()
    )

    # ── Requête 3 : observations non lues (directeur/staff uniquement) ───────
    unread_observations_count = 0
    if request.user.role in ('director', 'staff') or request.user.is_superuser:
        from apps.teachers.models import StudentObservation
        unread_observations_count = StudentObservation.objects.filter(
            school=school, is_read=False,
        ).count()

    return {
        'badge_year':                active_year,
        'alert_count':               alert_count,
        'unread_observations_count': unread_observations_count,
    }
