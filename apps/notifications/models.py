from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationCategory(models.TextChoices):
    OBSERVATION = 'observation', _('Observation partagée')
    ABSENCE     = 'absence',     _('Absence')
    BULLETIN    = 'bulletin',    _('Bulletin disponible')
    PAYMENT     = 'payment',     _('Paiement reçu')
    INFO        = 'info',        _("Message de l'école")


class Notification(models.Model):
    """
    Notification destinée à un utilisateur (parent, admin…).
    Découplée des modèles métier via GenericForeignKey : l'app notifications
    ne dépend que de accounts + schools + contenttypes (zéro cycle).
    title/body/url sont dénormalisés → la notif survit à la suppression de la cible.
    """
    recipient = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='notifications', verbose_name=_('destinataire'),
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='notifications', verbose_name=_('école'),
    )
    category = models.CharField(
        _('catégorie'), max_length=20,
        choices=NotificationCategory.choices, default=NotificationCategory.INFO,
    )
    title = models.CharField(_('titre'), max_length=200)
    body  = models.TextField(_('contenu'), blank=True)
    url   = models.CharField(_('lien'), max_length=300, blank=True)

    # Cible générique découplée (optionnelle)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('content_type', 'object_id')

    is_read    = models.BooleanField(_('lue'), default=False)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read'], name='notif_recipient_read_idx'),
            models.Index(fields=['school', 'category'],   name='notif_school_cat_idx'),
        ]

    def __str__(self):
        return f'[{self.get_category_display()}] {self.title} → {self.recipient.full_name}'
