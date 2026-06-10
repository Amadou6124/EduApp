from django.contrib.auth.backends import BaseBackend

from .models import User


class PhoneBackend(BaseBackend):
    """
    Authentification par numéro de téléphone au lieu de username/email.
    Utilisé comme backend principal — ModelBackend gardé en fallback
    pour le superadmin Django.
    """

    def authenticate(self, request, phone_number=None, password=None, **kwargs):
        if not phone_number or not password:
            return None

        try:
            user = User.objects.select_related('school').get(phone_number=phone_number)
        except User.DoesNotExist:
            # Exécuter le hashage pour limiter les attaques temporelles
            User().set_password(password)
            return None

        if not user.check_password(password):
            return None

        return user

    def get_user(self, user_id):
        try:
            return User.objects.select_related('school').get(pk=user_id)
        except User.DoesNotExist:
            return None
