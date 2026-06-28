import datetime
from decimal import Decimal

from django.db.models import (
    Count, F, OuterRef, Q, Subquery, Sum, DecimalField
)
from django.db.models.functions import Coalesce

from apps.accounts.models import UserRole


def school_context(request):
    """
    Injecte dans chaque template :
      - active_year  : SchoolYear active (avec .period_name annoté)
      - alert_count  : nb d'élèves EN RETARD (≥ 1 tranche échue impayée — nouveau
                       modèle, cohérent avec la liste rouge du lot 6)

    Performance : 2 requêtes SQL par page authentifiée avec école.
      Req 1 — SchoolYear (LIMIT 1) + prefetch Period → 2 SQL internes, 1 unité logique
      Req 2 — COUNT distinct des élèves ayant une tranche échue impayée (due_date indexée)
    """
    if not request.user.is_authenticated:
        return {}

    # Rôle affiché (avatar sidebar) : label du rôle de l'école ACTIVE
    # (request.role est per-école via get_active_role), pas le User.role global.
    active_role_display = ''
    role = getattr(request, 'role', None)
    if role:
        from apps.accounts.models import UserRole
        try:
            active_role_display = UserRole(role).label
        except ValueError:
            active_role_display = ''

    school = getattr(request, 'school', None)
    if not school:
        return {'active_role_display': active_role_display}

    from apps.schools.models import SchoolYear, Period
    from apps.finance.models import Installment

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

    # ── Requête 2 : élèves EN RETARD — NOUVEAU modèle (lot 6 finition) ─────────
    # alert_count = nb d'élèves ayant ≥ 1 tranche échue impayée (due_date < today ET
    # solde > 0), exactement la définition de la liste rouge du lot 6 (cohérence du
    # badge cloche avec l'onglet « En retard »). Les élèves sans fiche n'ont aucune
    # tranche → ignorés proprement. 1 requête (distinct count), due_date indexée.
    alert_count = (
        Installment.objects
        .filter(debt__account__enrollment__school=school,
                debt__account__enrollment__status='active',
                debt__account__enrollment__student__is_active=True,
                debt__is_active=True, due_date__lt=today)
        .annotate(allocated=Coalesce(Sum('allocations__amount'),
                                     Decimal('0'), output_field=DecimalField()))
        .annotate(remaining=F('amount_due') - F('allocated'))
        .filter(remaining__gt=0)
        .values('debt__account__enrollment__student_id')
        .distinct()
        .count()
    )

    # ── Requête 3 : observations non lues (directeur/staff uniquement) ───────
    unread_observations_count = 0
    if request.role in (UserRole.DIRECTOR, UserRole.STAFF) or request.user.is_superuser:
        from apps.teachers.models import StudentObservation
        unread_observations_count = StudentObservation.objects.filter(
            school=school, is_read=False, is_private=False,
        ).count()

    # ── Requête 4 : autres écoles de l'utilisateur (switch multi-école) ──────
    from apps.accounts.models import Membership
    user_memberships = list(
        Membership.objects
        .filter(user=request.user, is_active=True)
        .select_related('school')
        .exclude(school=school)
        .order_by('school__name')
    )

    return {
        'badge_year':                active_year,
        'alert_count':               alert_count,
        'unread_observations_count': unread_observations_count,
        'user_memberships':          user_memberships,
        'active_role_display':       active_role_display,
    }
