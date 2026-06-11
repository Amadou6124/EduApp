import random
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_student_access_code():
    """Génère un code d'accès à 6 chiffres. L'unicité par école est garantie par unique_together."""
    return str(random.randint(100000, 999999))


class ParentRelationship(models.TextChoices):
    FATHER   = 'father',   _('Père')
    MOTHER   = 'mother',   _('Mère')
    GUARDIAN = 'guardian', _('Tuteur/Tutrice')


class Student(models.Model):
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.PROTECT,
        related_name='students',
        verbose_name=_('école'),
    )
    school_class = models.ForeignKey(
        'schools.SchoolClass',
        on_delete=models.PROTECT,
        related_name='students',
        verbose_name=_('classe'),
    )
    # db_index pour accélérer recherche et tri
    full_name = models.CharField(_('nom complet'), max_length=200, db_index=True)
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
    parent_relationship = models.CharField(
        _('lien de parenté'),
        max_length=10,
        choices=ParentRelationship.choices,
        blank=True,
    )
    # Code à 6 chiffres, unique par école (contrainte unique_together dans Meta)
    access_code = models.CharField(
        _('code d\'accès'),
        max_length=6,
        default=generate_student_access_code,
        editable=False,
    )
    # Frais copiés de la classe au moment de l'inscription
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
        # Code d'accès unique au sein d'une école
        unique_together = [('school', 'access_code')]
        indexes = [
            models.Index(fields=['school', 'school_class'], name='student_school_class_idx'),
            models.Index(fields=['school', 'is_active'],    name='student_school_active_idx'),
        ]

    def __str__(self):
        return f'{self.full_name} — {self.school_class.name}'

    # ── Méthodes financières ──────────────────────────────────────────────
    # Utilisent self.payments.all() pour bénéficier du prefetch_related cache.
    # Dans les vues de liste, préfetcher avec :
    #   .prefetch_related('payments')
    # Aucune requête supplémentaire ne sera émise.

    def get_total_paid(self):
        return sum(p.amount for p in self.payments.all() if not p.is_cancelled)

    def get_balance_due(self):
        return self.tuition_fee - self.get_total_paid()

    def get_payment_status(self):
        paid = self.get_total_paid()
        if paid >= self.tuition_fee:
            return 'paid'
        if paid > 0:
            return 'partial'
        return 'unpaid'

    def has_parent_linked(self):
        return bool(self.parent_phone_number)

    def get_avatar_colors(self):
        """Retourne (bg, text) selon la première lettre du nom (A-E/F-J/K-O/P-T/U-Z)."""
        letter = self.full_name[0].upper() if self.full_name else 'A'
        if letter <= 'E':
            return '#E6F1FB', '#0C447C'
        if letter <= 'J':
            return '#EAF3DE', '#27500A'
        if letter <= 'O':
            return '#FAEEDA', '#633806'
        if letter <= 'T':
            return '#EEEDFE', '#3C3489'
        return '#FAECE7', '#712B13'

    def get_initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return f'{parts[0][0]}{parts[-1][0]}'.upper()
        return self.full_name[:2].upper() if self.full_name else '??'
