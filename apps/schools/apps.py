from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SchoolsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.schools'
    verbose_name = _('Écoles et classes')
