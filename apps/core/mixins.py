from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponseForbidden
from django.urls import reverse


class _NoSchoolError(Exception):
    """Levée quand un utilisateur sans école (superadmin) accède à une vue métier."""
    pass


def get_school(request):
    """
    Retourne l'école de l'utilisateur connecté.
    Point d'entrée unique pour l'isolation multi-tenant dans les vues FBV.
    Lève _NoSchoolError si l'utilisateur n'a pas d'école (ex: superadmin).
    Interceptée par SchoolMiddleware → redirect /superadmin/.
    """
    school = request.user.school
    if school is None:
        raise _NoSchoolError()
    return school


def director_or_staff_required(view_func):
    """Limite l'accès aux directeurs, staff et superadmins. À placer après @login_required."""
    from django.shortcuts import redirect

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('accounts:login') + f'?next={request.path}')
        if request.user.role not in ('director', 'staff') and not request.user.is_superuser:
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
