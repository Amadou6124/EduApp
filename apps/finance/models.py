"""
Module Finances — Lot 2 : catalogue de frais (niveau école).

Vue d'ensemble du domaine (ce lot pose la FONDATION, consommée par l'inscription au
lot 4 et l'échéancier au lot 3) :

  FeeType                  → le catalogue : « quels frais existent dans cette école »
    └─ FeeVariant          → options tarifées d'un frais (trajets bus, genre tenue…)
  PaymentScheduleTemplate  → gabarits de découpage en tranches de la scolarité

Contrats de données clés (lire avant de modifier) :
  - La SCOLARITÉ (category=TUITION) ne stocke JAMAIS son montant ici : il vit sur
    SchoolClass.annual_fee. Le catalogue ne fait que déclarer « la scolarité existe »
    et comment elle sera découpée (via un PaymentScheduleTemplate).
  - Les frais À VARIANTES (has_variants=True) ne stockent pas non plus de montant sur
    le FeeType : chaque montant vit dans une FeeVariant.
  - Donc default_amount n'est renseigné QUE pour un frais simple, à montant unique,
    non-scolarité (ex. Inscription, Fournitures).
"""
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class FeeCategory(models.TextChoices):
    # Frais ponctuel, dû une fois (inscription, fournitures, tenue). Réglé en une ou
    # plusieurs fois mais sans logique d'abonnement.
    ONE_TIME     = 'one_time',     _('Frais ponctuel')
    # Scolarité : montant porté par SchoolClass.annual_fee, découpé en tranches par un
    # gabarit. Aucun montant stocké sur le FeeType (cf. contrat ci-dessus).
    TUITION      = 'tuition',      _('Scolarité')
    # Abonnement récurrent résiliable (bus, cantine) : mensuel ou forfait annuel.
    # Volontairement distinct des tranches de scolarité (décision actée au plan).
    SUBSCRIPTION = 'subscription', _('Abonnement')


class FeeType(models.Model):
    """Un type de frais déclaré au catalogue d'une école."""

    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='fee_types', verbose_name=_('école'),
    )
    name = models.CharField(
        _('nom'), max_length=100,
        help_text=_('Ex : Inscription, Cantine, Bus, Tenue, Fournitures'),
    )
    category = models.CharField(
        _('catégorie'), max_length=20,
        choices=FeeCategory.choices, default=FeeCategory.ONE_TIME,
    )
    # Montant pour un frais SIMPLE uniquement. NULL si :
    #   - category = TUITION (montant = SchoolClass.annual_fee), ou
    #   - has_variants = True (montants portés par les FeeVariant).
    default_amount = models.DecimalField(
        _('montant (FCFA)'), max_digits=10, decimal_places=0,
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text=_('Laisser vide pour la scolarité et les frais à variantes.'),
    )
    # True  = appliqué automatiquement à TOUS les élèves à l'inscription (inscription).
    # False = optionnel, coché au cas par cas à l'inscription (cantine, bus).
    is_mandatory = models.BooleanField(
        _('obligatoire'), default=False,
        help_text=_('Appliqué automatiquement à tous les élèves.'),
    )
    # True = le prix dépend d'une variante (tenue, bus) → voir FeeVariant.
    has_variants = models.BooleanField(
        _('à variantes'), default=False,
        help_text=_('Le montant dépend d\'une option (trajet, genre, formule).'),
    )
    # True  = la variante est choisie AUTOMATIQUEMENT selon Student.gender (tenue).
    # False = variante choisie manuellement à l'inscription (bus, formules cantine).
    # N'a de sens que si has_variants=True.
    is_gender_based = models.BooleanField(
        _('selon le genre'), default=False,
        help_text=_('La variante est choisie automatiquement selon le genre de l\'élève.'),
    )
    # Désactivation douce : retire le frais des nouvelles inscriptions sans casser
    # l'historique des fiches financières qui le référencent déjà.
    is_active = models.BooleanField(_('actif'), default=True)
    order = models.PositiveSmallIntegerField(_('ordre d\'affichage'), default=0)
    created_at = models.DateTimeField(_('créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('type de frais')
        verbose_name_plural = _('types de frais')
        ordering = ['order', 'name']
        constraints = [
            # Nom unique par école — MAIS seulement parmi les frais ACTIFS.
            # Condition is_active=True : un frais désactivé libère son nom, ce qui
            # permet de le réactiver (ou d'en recréer un) sans collision. On ne
            # supprime jamais un frais (il pourra porter des paiements) : on le
            # désactive / réactive.
            models.UniqueConstraint(
                fields=['school', 'name'],
                condition=models.Q(is_active=True),
                name='uniq_active_fee_type_school_name',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active'], name='feetype_school_active_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.school.name})'

    # Icône Lucide pour le catalogue (décorative). Choix par mot-clé du nom pour aider
    # au scan visuel, repli sur la catégorie. Cohérent avec le set Lucide de l'app.
    def get_icon(self):
        n = (self.name or '').lower()
        if 'inscription' in n:           return 'clipboard-check'
        if 'scolar' in n:                return 'school'
        if 'fourniture' in n:            return 'book'
        if 'tenue' in n or 'uniforme' in n: return 'shirt'
        if 'bus' in n or 'transport' in n:  return 'bus'
        if 'cantine' in n or 'repas' in n:  return 'utensils'
        # Repli par catégorie
        if self.category == FeeCategory.TUITION:      return 'school'
        if self.category == FeeCategory.SUBSCRIPTION: return 'refresh-cw'
        return 'receipt'

    def clean(self):
        # Garde-fous de cohérence du contrat de données (cf. docstring du module).
        if self.category == FeeCategory.TUITION:
            # La scolarité ne porte ni montant ni variantes ici.
            if self.default_amount is not None:
                raise ValidationError({
                    'default_amount': _('La scolarité ne stocke pas de montant ici '
                                        '(il vient de la classe).'),
                })
        if self.has_variants and self.default_amount is not None:
            raise ValidationError({
                'default_amount': _('Un frais à variantes ne porte pas de montant '
                                    'global (le montant vit dans les variantes).'),
            })
        if self.is_gender_based and not self.has_variants:
            raise ValidationError({
                'is_gender_based': _('« Selon le genre » nécessite un frais à variantes.'),
            })

    @property
    def is_simple_amount(self):
        """True si le frais porte un montant unique éditable (ni scolarité ni variantes)."""
        return self.category != FeeCategory.TUITION and not self.has_variants


class FeeVariant(models.Model):
    """
    Option tarifée d'un frais à variantes.

    Exemples : un trajet de bus (« Badalabougou » → 20000), un genre de tenue
    (« Fille » → 15000), une formule cantine (« Repas complet » → 5000).

    Pour un frais is_gender_based=True (tenue), gender_key ('M'/'F') relie la variante
    au champ Student.gender (lot 1) : à l'inscription, on choisira automatiquement la
    variante dont gender_key == student.gender. Pour les variantes non genrées (bus,
    cantine), gender_key reste NULL et le choix est manuel.
    """
    fee_type = models.ForeignKey(
        FeeType, on_delete=models.CASCADE,
        related_name='variants', verbose_name=_('type de frais'),
    )
    label = models.CharField(
        _('libellé'), max_length=100,
        help_text=_('Ex : Badalabougou, Fille, Garçon, Repas complet'),
    )
    amount = models.DecimalField(
        _('montant (FCFA)'), max_digits=10, decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    # Code genre ('M' / 'F') — réutilise les codes de students.Gender (lot 1).
    # Renseigné uniquement pour les variantes d'un frais is_gender_based.
    gender_key = models.CharField(
        _('genre'), max_length=1,
        null=True, blank=True,
    )
    is_active = models.BooleanField(_('active'), default=True)
    order = models.PositiveSmallIntegerField(_('ordre d\'affichage'), default=0)

    class Meta:
        verbose_name = _('variante de frais')
        verbose_name_plural = _('variantes de frais')
        ordering = ['order', 'label']
        constraints = [
            # Libellé unique par frais — parmi les variantes ACTIVES uniquement.
            # Même logique que FeeType : une variante désactivée libère son libellé.
            # Permet d'ÉDITER une variante (même pk → pas de collision) et de
            # réactiver sans buter sur « existe déjà ».
            models.UniqueConstraint(
                fields=['fee_type', 'label'],
                condition=models.Q(is_active=True),
                name='uniq_active_fee_variant_type_label',
            ),
        ]
        indexes = [
            models.Index(fields=['fee_type', 'is_active'], name='feevariant_type_active_idx'),
        ]

    def __str__(self):
        return f'{self.fee_type.name} — {self.label} ({self.amount} FCFA)'


class PaymentScheduleTemplate(models.Model):
    """
    Gabarit de découpage de la SCOLARITÉ en tranches, au niveau école.

    Contrat : ce gabarit ne stocke aucun montant. Il sert uniquement à GÉNÉRER les
    lignes d'échéancier à l'inscription (lots 3/4) en divisant SchoolClass.annual_fee
    en `installments_count` tranches. Le gabarit is_default=True est celui appliqué
    par défaut ; il restera surchargeable élève par élève plus tard.
    """
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='schedule_templates', verbose_name=_('école'),
    )
    name = models.CharField(
        _('nom'), max_length=50,
        help_text=_('Ex : Annuel, Trimestriel, Mensuel'),
    )
    installments_count = models.PositiveSmallIntegerField(
        _('nombre de tranches'),
        validators=[MinValueValidator(1)],
        help_text=_('1 = paiement unique, 3 = trimestriel, 9 = mensuel…'),
    )
    # Un seul gabarit par défaut par école (garanti par save() + contrainte unique).
    is_default = models.BooleanField(_('par défaut'), default=False)
    is_active = models.BooleanField(_('actif'), default=True)
    created_at = models.DateTimeField(_('créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('gabarit de tranches')
        verbose_name_plural = _('gabarits de tranches')
        ordering = ['installments_count']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                name='uniq_schedule_template_school_name',
            ),
            # Au plus UN gabarit par défaut par école. Contrainte partielle :
            # ne s'applique qu'aux lignes is_default=True.
            models.UniqueConstraint(
                fields=['school'],
                condition=models.Q(is_default=True),
                name='uniq_default_schedule_per_school',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.installments_count} tranches) — {self.school.name}'

    def clean(self):
        # Cohérence applicative : interdit un 2e gabarit par défaut côté logique métier
        # (la contrainte DB le garantit aussi, mais on remonte un message clair).
        if self.is_default:
            qs = PaymentScheduleTemplate.objects.filter(
                school=self.school, is_default=True,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    _('Un seul gabarit par défaut est autorisé par école.')
                )

    def save(self, *args, **kwargs):
        # Si on passe ce gabarit en défaut, on retire le flag des autres de la même
        # école dans la même transaction logique → bascule atomique côté application,
        # et la contrainte DB partielle reste satisfaite.
        if self.is_default:
            PaymentScheduleTemplate.objects.filter(
                school=self.school, is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
