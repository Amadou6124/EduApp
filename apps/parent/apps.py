from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ParentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.parent'
    verbose_name = _('Espace Parent')
