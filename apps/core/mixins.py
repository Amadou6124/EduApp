from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponseForbidden
from django.urls import reverse


class _NoSchoolError(Exception):
    """Levée quand un utilisateur sans école (superadmin) accède à une vue métier."""
    pass


class _PromoterNoSchoolError(_NoSchoolError):
    """Promoteur (owner de SchoolGroup) sans école active → rediriger vers /promoter/."""
    pass


class _ParentNoSchoolError(_NoSchoolError):
    """Parent (role=parent) sans école active → rediriger vers /portal/parent/."""
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
    # 1. Cache par requête : succès (_active_school) OU échec (_active_school_error).
    #    Évite de re-requêter quand get_school est rappelé (middleware, get_active_role,
    #    décorateurs) pour un user sans école (promoteur, superadmin).
    if hasattr(request, '_active_school'):
        return request._active_school
    if hasattr(request, '_active_school_error'):
        raise request._active_school_error

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
        # Aucune école : promoteur / parent / superadmin → exception dédiée.
        # Cachée sur la requête pour ne pas re-requêter aux appels suivants.
        if request.user.owned_groups.exists():
            exc = _PromoterNoSchoolError()
        elif request.user.role == 'parent':
            exc = _ParentNoSchoolError()
        else:
            exc = _NoSchoolError()
        request._active_school_error = exc
        raise exc

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


def director_or_accounting_required(view_func):
    """
    Réservé au directeur (rôle actif), superadmin, ou détenteur de
    StaffPermission.can_manage_accounting. Sinon 403. À placer après @login_required.
    """
    from django.shortcuts import redirect

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('accounts:login') + f'?next={request.path}')
        allowed = (
            get_active_role(request) == 'director'
            or request.user.is_superuser
        )
        if not allowed:
            sp = getattr(request.user, 'staff_permission', None)
            allowed = bool(sp and sp.can_manage_accounting)
        if not allowed:
            return HttpResponseForbidden(
                '<h1 style="font-family:sans-serif;padding:40px">403 — Accès comptabilité réservé.</h1>'
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def promoter_required(view_func):
    """
    Réservé aux promoteurs : rôle actif 'promoter', OU propriétaire d'au moins
    un SchoolGroup, OU superadmin. Sinon → dashboard standard.
    À placer après @login_required.
    """
    from django.shortcuts import redirect

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('accounts:login') + f'?next={request.path}')
        is_promoter = (
            get_active_role(request) == 'promoter'
            or request.user.owned_groups.exists()
            or request.user.is_superuser
        )
        if not is_promoter:
            return redirect('dashboard:main')
        return view_func(request, *args, **kwargs)
    return wrapper


def parent_required(view_func):
    """
    Réservé aux parents (rôle actif/legacy 'parent') et superadmins.
    Sinon → login. À placer après @login_required.
    """
    from django.shortcuts import redirect

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('accounts:login') + f'?next={request.path}')
        is_parent = (
            get_active_role(request) == 'parent'
            or request.user.role == 'parent'
            or request.user.is_superuser
        )
        if not is_parent:
            return redirect('accounts:login')
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
