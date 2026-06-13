from django.contrib import messages
from django.shortcuts import redirect

from .mixins import (
    _NoSchoolError, _PromoterNoSchoolError, _ParentNoSchoolError,
    get_school, get_active_role,
)


class SchoolMiddleware:
    """
    Attache l'école active et le rôle per-école à la request pour accès direct
    dans les templates.

    Intercepte via process_exception les exceptions levées par les vues métier
    quand l'utilisateur n'a pas d'école active :
      - _PromoterNoSchoolError → /promoter/ (promoteur pur)
      - _NoSchoolError         → /superadmin/ (superadmin sans école)

    NB : on utilise process_exception (et non un try/except autour de
    get_response) car Django enveloppe chaque middleware dans
    convert_exception_to_response, qui capture les exceptions de vue avant
    qu'elles n'atteignent le __call__. process_exception est le hook prévu.

    Doit être placé après AuthenticationMiddleware dans MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # École active multi-école (session → défaut → première → legacy).
            # _NoSchoolError est tolérée ici : request.school=None ; l'interception
            # avec redirection se fait dans process_exception sur la vue métier.
            try:
                request.school = get_school(request)
            except _NoSchoolError:
                request.school = None
            request.role = get_active_role(request)
        else:
            request.school = None
            request.role = None
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Sous-classes d'abord (toutes héritent de _NoSchoolError).
        if isinstance(exception, _PromoterNoSchoolError):
            return redirect('/promoter/')
        if isinstance(exception, _ParentNoSchoolError):
            return redirect('/portal/parent/')
        if isinstance(exception, _NoSchoolError):
            messages.warning(
                request,
                "Les pages de gestion ne sont pas accessibles depuis le compte superadmin. "
                "Connectez-vous en tant que directeur d'école."
            )
            return redirect('/superadmin/')
        return None
