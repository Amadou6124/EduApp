from django.contrib.auth.mixins import AccessMixin


def get_school(request):
    """
    Retourne l'école de l'utilisateur connecté.
    Point d'entrée unique pour l'isolation multi-tenant dans les vues FBV.
    Remplace tous les anciens get_demo_school() / _get_school().
    """
    return request.user.school


class SchoolMixin(AccessMixin):
    """
    Mixin pour les vues basées sur les classes (CBV).
    Injecte automatiquement l'école et filtre le queryset.
    """

    def get_school(self):
        return self.request.user.school

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(school=self.get_school())
