from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _


class PaymentMethod(models.TextChoices):
    CASH = 'cash', _('Espèces')
    MOBILE_MONEY = 'mobile_money', _('Mobile Money')
    BANK_TRANSFER = 'bank_transfer', _('Virement bancaire')
    CHECK = 'check', _('Chèque')


class Payment(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('élève'),
    )
    amount = models.DecimalField(
        _('montant versé (FCFA)'),
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(1)],
    )
    payment_method = models.CharField(
        _('mode de paiement'),
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    paid_at = models.DateTimeField(_('date du versement'), auto_now_add=True)
    # Référence pour le reçu PDF
    receipt_number = models.CharField(_('numéro de reçu'), max_length=50, unique=True)
    # Collecté par quel membre du staff
    collected_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='collected_payments',
        verbose_name=_('encaissé par'),
    )
    notes = models.TextField(_('notes'), blank=True)
    # Permet d'annuler un paiement sans le supprimer
    is_valid = models.BooleanField(_('valide'), default=True)

    class Meta:
        verbose_name = _('paiement')
        verbose_name_plural = _('paiements')
        ordering = ['-paid_at']

    def __str__(self):
        return f'Reçu {self.receipt_number} — {self.student.full_name} ({self.amount} FCFA)'

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self._generate_receipt_number()
        super().save(*args, **kwargs)

    def _generate_receipt_number(self):
        import uuid
        return f'REC-{uuid.uuid4().hex[:10].upper()}'
