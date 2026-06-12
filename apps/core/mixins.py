from django.contrib.auth.mixins import AccessMixin


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
