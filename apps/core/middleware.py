from django.contrib import messages
from django.shortcuts import redirect

from .mixins import _NoSchoolError, get_school, get_active_role


class SchoolMiddleware:
    """
    Attache l'école active et le rôle per-école à la request pour accès direct
    dans les templates. Intercepte aussi _NoSchoolError (superadmin sans école
    sur une vue métier) et redirige vers /superadmin/ avec un message explicite.
    Doit être placé après AuthenticationMiddleware dans MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # École active multi-école (session → défaut → première → legacy).
            # _NoSchoolError (superadmin) est tolérée ici : request.school=None,
            # l'interception se fait sur la vue métier plus bas.
            try:
                request.school = get_school(request)
            except _NoSchoolError:
                request.school = None
            request.role = get_active_role(request)
        else:
            request.school = None
            request.role = None
        try:
            response = self.get_response(request)
        except _NoSchoolError:
            messages.warning(
                request,
                "Les pages de gestion ne sont pas accessibles depuis le compte superadmin. "
                "Connectez-vous en tant que directeur d'école."
            )
            return redirect('/superadmin/')
        return response
