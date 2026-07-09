"""Middleware d'authentification transverses."""
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Force le choix d'un mot de passe personnel avant tout accès.

    Un compte marqué `must_change_password` (mot de passe temporaire posé par l'école lors
    de la création / réinitialisation d'un compte parent) ne peut RIEN faire tant qu'il n'a
    pas choisi son propre mot de passe. Seuls la page de choix, la déconnexion et les statiques
    passent ; tout le reste redirige. C'est ce qui fait mourir le temporaire après un seul usage.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._allowed = None

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and getattr(user, 'must_change_password', False):
            if self._allowed is None:  # résolu une fois (les URLs ne changent pas)
                self._allowed = {reverse('accounts:password-set'), reverse('accounts:logout')}
            if request.path not in self._allowed and not request.path.startswith(('/static/', '/media/')):
                return redirect('accounts:password-set')
        return self.get_response(request)
