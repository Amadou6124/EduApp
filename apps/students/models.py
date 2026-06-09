import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_student_access_code():
    return uuid.uuid4().hex[:8].upper()


class Student(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='students',
        verbose_name=_('école'),
    )
    school_class = models.ForeignKey(
        'schools.SchoolClass',
        on_delete=models.PROTECT,
        related_name='students',
        verbose_name=_('classe'),
    )
    full_name = models.CharField(_('nom complet'), max_length=200)
    date_of_birth = models.DateField(_('date de naissance'), null=True, blank=True)
    phone_number = models.CharField(
        _('téléphone élève'),
        max_length=20,
        blank=True,
    )
    parent_phone_number = models.CharField(
        _('téléphone parent'),
        max_length=20,
        blank=True,
    )
    # Code généré automatiquement à l'inscription
    access_code = models.CharField(
        _('code d\'accès'),
        max_length=8,
        unique=True,
        default=generate_student_access_code,
        editable=False,
    )
    # Frais hérités de la classe au moment de l'inscription
    tuition_fee = models.DecimalField(
        _('frais de scolarité (FCFA)'),
        max_digits=10,
        decimal_places=0,
    )
    notes = models.TextField(_('informations supplémentaires'), blank=True)
    is_active = models.BooleanField(_('actif'), default=True)
    enrolled_at = models.DateTimeField(_('inscrit le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('modifié le'), auto_now=True)

    class Meta:
        verbose_name = _('élève')
        verbose_name_plural = _('élèves')
        ordering = ['full_name']

    def __str__(self):
        return f'{self.full_name} — {self.school_class.name}'

    def get_total_paid(self):
        return sum(p.amount for p in self.payments.filter(is_valid=True))

    def get_balance_due(self):
        return self.tuition_fee - self.get_total_paid()

    def get_payment_status(self):
        balance = self.get_balance_due()
        if balance <= 0:
            return 'paid'
        if self.get_total_paid() > 0:
            return 'partial'
        return 'unpaid'

    def has_parent_linked(self):
        return bool(self.parent_phone_number)
