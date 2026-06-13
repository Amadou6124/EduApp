from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PromoterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.promoter'
    verbose_name = _('Promoteur')
