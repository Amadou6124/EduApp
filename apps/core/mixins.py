from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponseForbidden
from django.urls import reverse


class _NoSchoolError(Exception):
    """Levée quand un utilisateur sans école (superadmin) accède à une vue métier."""
    pass


def get_school(request):
    """
    Retourne l'école ACTIVE de l'utilisateur connecté (multi-école).
    Point d'entrée unique pour l'isolation multi-tenant dans les vues FBV.

    Ordre de résolution :
      1. cache requête (request._active_school)
      2. école de la session (active_school_id) si l'accès est toujours valide
      3. école par défaut (Membership.is_default)
      4. première appartenance active
      5. fallback legacy User.school (compatibilité transitoire Phase C)
    Lève _NoSchoolError si aucune école (ex: superadmin) → redirect /superadmin/.
    """
    # 1. Cache par requête
    if hasattr(request, '_active_school'):
        return request._active_school

    if not request.user.is_authenticated:
        raise _NoSchoolError()

    from apps.accounts.models import Membership

    active_id = request.session.get('active_school_id')

    memberships = Membership.objects.filter(
        user=request.user,
        is_active=True,
    ).select_related('school')

    membership = None
    if active_id:
        # 2. Valider que l'utilisateur a TOUJOURS accès à cette école
        membership = memberships.filter(school_id=active_id).first()

    if membership is None:
        # 3. École par défaut
        membership = memberships.filter(is_default=True).first()

    if membership is None:
        # 4. Première appartenance active
        membership = memberships.first()

    if membership is None:
        # 5. Fallback legacy : User.school direct (transitoire Phase C)
        if request.user.school:
            request._active_school = request.user.school
            return request.user.school
        raise _NoSchoolError()

    request._active_school = membership.school
    request._active_membership = membership

    # Resynchroniser la session si l'école effective diffère
    if active_id != membership.school_id:
        request.session['active_school_id'] = membership.school_id

    return membership.school


def get_active_role(request):
    """
    Retourne le rôle de l'utilisateur POUR L'ÉCOLE ACTIVE.
    Fallback sur User.role si aucun membership (compatibilité transitoire).
    """
    if hasattr(request, '_active_membership'):
        return request._active_membership.role

    # Déclenche get_school() pour peupler _active_membership
    try:
        get_school(request)
        if hasattr(request, '_active_membership'):
            return request._active_membership.role
    except _NoSchoolError:
        pass

    return request.user.role  # fallback legacy


def director_or_staff_required(view_func):
    """Limite l'accès aux directeurs, staff et superadmins. À placer après @login_required."""
    from django.shortcuts import redirect

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('accounts:login') + f'?next={request.path}')
        # Rôle de l'école active (multi-école), fallback legacy User.role
        if get_active_role(request) not in ('director', 'staff') and not request.user.is_superuser:
            return HttpResponseForbidden(
                '<h1 style="font-family:sans-serif;padding:40px">403 — Accès réservé au directeur et au staff.</h1>'
            )
        return view_func(request, *args, **kwargs)
    return wrapper


class SchoolMixin(AccessMixin):
    """
    Mixin pour les vues basées sur les classes (CBV).
    Injecte automatiquement l'école et filtre le queryset.
    """

    def get_school(self):
        school = self.request.user.school
        if school is None:
            raise _NoSchoolError()
        return school

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(school=self.get_school())
