from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StudentLearningConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.student_learning'
    verbose_name = _('Apprentissage élève')
