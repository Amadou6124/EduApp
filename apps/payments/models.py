import datetime

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PaymentMethod(models.TextChoices):
    CASH         = 'cash',         _('Espèces')
    ORANGE_MONEY = 'orange_money', _('Orange Money')
    WAVE         = 'wave',         _('Wave')
    OTHER        = 'other',        _('Autre')


class Payment(models.Model):
    # ── Élève ──────────────────────────────────────────────────────
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('élève'),
    )

    # ── Montant ────────────────────────────────────────────────────
    amount = models.DecimalField(
        _('montant versé (FCFA)'),
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(1)],
    )

    # ── Date et mode ───────────────────────────────────────────────
    payment_date = models.DateField(
        _('date du versement'),
        default=datetime.date.today,
        db_index=True,
    )
    payment_method = models.CharField(
        _('mode de paiement'),
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )

    # ── Reçu ───────────────────────────────────────────────────────
    receipt_number = models.CharField(
        _('numéro de reçu'), max_length=50, unique=True, blank=True,
    )

    # ── Collecte ───────────────────────────────────────────────────
    collected_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='collected_payments',
        verbose_name=_('encaissé par'),
    )
    notes = models.TextField(_('notes'), blank=True)

    # ── Annulation (soft delete) ────────────────────────────────────
    is_cancelled = models.BooleanField(_('annulé'), default=False, db_index=True)
    cancelled_at = models.DateTimeField(_('annulé le'), null=True, blank=True)
    cancellation_reason = models.TextField(_('motif d\'annulation'), blank=True)

    # ── Audit ──────────────────────────────────────────────────────
    created_at = models.DateTimeField(_('créé le'), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _('paiement')
        verbose_name_plural = _('paiements')
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['student', 'is_cancelled']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return f'Reçu {self.receipt_number} — {self.student.full_name} ({self.amount} FCFA)'

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self._generate_receipt_number()
        super().save(*args, **kwargs)

    def _generate_receipt_number(self):
        """Génère REC-YYYY-XXXX — séquentiel par année."""
        year = datetime.date.today().year
        last = (
            Payment.objects
            .filter(receipt_number__startswith=f'REC-{year}-')
            .order_by('-receipt_number')
            .values_list('receipt_number', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.split('-')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'REC-{year}-{seq:04d}'
