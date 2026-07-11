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
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from apps.schools.models import EducationLevel


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


class AppliesTo(models.TextChoices):
    # À qui le frais s'applique AUTOMATIQUEMENT à l'inscription. La reconnaissance
    # nouveau / ancien est faite par le socle temporel (lot 1) : un élève est ANCIEN
    # s'il possède déjà un StudentEnrollment pour l'année précédente dans la même école.
    NEW       = 'new',       _('Nouveaux élèves')        # uniquement les nouveaux inscrits
    RETURNING = 'returning', _('Anciens élèves')          # uniquement les réinscriptions
    ALL       = 'all',       _('Tous')                    # tout le monde (défaut)


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
    # ── Règle nouveaux / anciens (lot 3) ──────────────────────────────────────
    # À quels élèves ce frais s'applique automatiquement à l'inscription, selon qu'ils
    # ont (ANCIEN) ou non (NOUVEAU) un StudentEnrollment l'année précédente. Défaut ALL.
    applies_to = models.CharField(
        _('s\'applique à'), max_length=10,
        choices=AppliesTo.choices, default=AppliesTo.ALL,
    )
    # Tarif réduit OPTIONNEL pour les anciens (réinscription). Si NULL, on applique
    # default_amount (ou la variante) à tout le monde, ancien comme nouveau.
    returning_amount = models.DecimalField(
        _('tarif réinscription (FCFA)'), max_digits=10, decimal_places=0,
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text=_('Montant réduit pour les anciens élèves. Vide = même tarif pour tous.'),
    )
    # Niveaux (EducationLevel) auxquels ce frais s'applique. Liste VIDE = TOUS les niveaux
    # (rétro-compatible : les frais existants restent « tous niveaux »). Ex. « Inscription
    # préscolaire » → ['prescolaire']. Les valeurs sont validées contre EducationLevel au
    # formulaire (pas de faute de frappe possible). 2e axe de ciblage, indépendant de applies_to.
    applies_to_levels = ArrayField(
        models.CharField(max_length=20, choices=EducationLevel.choices),
        verbose_name=_('niveaux concernés'), blank=True, default=list,
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

    def applies_to_student(self, is_returning):
        """
        Ce frais s'applique-t-il automatiquement à un élève selon son statut ?
        is_returning=True → ancien (réinscription), False → nouveau.
        ALL → toujours ; NEW → nouveaux seulement ; RETURNING → anciens seulement.
        """
        if self.applies_to == AppliesTo.ALL:
            return True
        if self.applies_to == AppliesTo.NEW:
            return not is_returning
        return is_returning  # RETURNING

    def applies_to_level(self, level):
        """Ce frais concerne-t-il ce niveau ? Liste vide = TOUS les niveaux."""
        return not self.applies_to_levels or level in self.applies_to_levels

    def get_levels_display(self):
        """Libellés des niveaux ciblés (' · ' séparé), ou '' si tous (liste vide)."""
        if not self.applies_to_levels:
            return ''
        labels = dict(EducationLevel.choices)
        return ' · '.join(str(labels.get(lvl, lvl)) for lvl in self.applies_to_levels)

    def is_applicable(self, school_class, is_returning):
        """Ce frais s'applique-t-il AUTOMATIQUEMENT à cette classe/élève ?

        Point d'entrée UNIQUE de la génération des frais : combine (ET) les deux axes de
        ciblage — statut nouveau/ancien (applies_to) ET niveau (applies_to_levels). Les
        dimensions futures (programme, campus…) s'ajouteront ici, sans toucher le service.
        """
        return (
            self.applies_to_student(is_returning)
            and self.applies_to_level(school_class.level)
        )

    def resolved_amount(self, is_returning, variant=None):
        """
        Montant à facturer pour ce frais à un élève donné.
        Priorité : variante (si fournie) > tarif réinscription (si ancien et défini) >
        montant simple. Renvoie None pour la scolarité (montant = classe, hors catalogue).
        """
        if variant is not None:
            return variant.amount
        if is_returning and self.returning_amount is not None:
            return self.returning_amount
        return self.default_amount


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
        # Bornes 1–12 au modèle (symétrie : le min y était déjà). NB Django : ces
        # validators ne s'exécutent QUE via full_clean() (donc via le formulaire) ; un
        # .create() brut passe outre. La vraie garantie « tous points d'entrée » serait
        # un CheckConstraint — volontairement non posé (inutile avant lancement).
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text=_('Entre 1 et 12. Ex : 1 = paiement unique, 3 = trimestriel, 9 = mensuel…'),
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
        # Garde `self.school_id` : full_clean() peut tourner via form.is_valid()
        # AVANT que la vue n'attache l'école → accéder à `self.school` lèverait un
        # 500. Le vrai contrôle a lieu au full_clean() suivant, école posée.
        if self.is_default and self.school_id:
            qs = PaymentScheduleTemplate.objects.filter(
                school_id=self.school_id, is_default=True,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    _('Un seul gabarit par défaut est autorisé par école.')
                )

    def save(self, *args, **kwargs):
        # Si on passe ce gabarit en défaut, on retire le flag des autres de la même
        # école. Enveloppé dans transaction.atomic : la démotion des autres et la
        # promotion de celui-ci forment UN tout → jamais d'état « zéro défaut » visible
        # (ni de démotion committée si le save échoue).
        if self.is_default:
            with transaction.atomic():
                PaymentScheduleTemplate.objects.filter(
                    school=self.school, is_default=True,
                ).exclude(pk=self.pk).update(is_default=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# LOT 3 — FICHE FINANCIÈRE PAR ANNÉE : dettes, échéancier, allocation
# ═══════════════════════════════════════════════════════════════════════════════
#
# Modèle de données (4 niveaux) — accroché à l'ANNÉE via StudentEnrollment :
#
#   StudentFeeAccount   (1 par enrollment = 1 élève × 1 année)
#     └─ FeeDebt        (1 dette ; kind ∈ {tuition, one_time, subscription})
#          └─ Installment   (1 échéance datée ; N pour la scolarité, 1 pour un ponctuel,
#                            1 par mois actif pour un abonnement)
#               └─ PaymentAllocation  (lien Payment ↔ Installment ; montant ventilé)
#
# CONTRAT D'IMMUABILITÉ (capital) :
#   - apps.payments.Payment reste un JOURNAL IMMUABLE : aucun champ « payé / alloué »
#     n'y est ajouté. Le lien paiement → dette passe UNIQUEMENT par PaymentAllocation.
#   - Aucun solde n'est stocké : tout solde (dette, tranche, fiche) se CALCULE en
#     agrégeant les PaymentAllocation. Les méthodes ci-dessous ne mutent jamais d'état.
#
# CONTRAT DES 3 FAMILLES (jamais fondues) :
#   - TUITION      : scolarité, total = SchoolClass.annual_fee (snapshot), découpée en
#                    N Installment datés par un PaymentScheduleTemplate.
#   - ONE_TIME     : frais ponctuel (inscription, fournitures, tenue), 1 Installment.
#   - SUBSCRIPTION : abonnement (bus, cantine), résiliable (is_active=False arrête la
#                    génération des mensualités) ; 1 Installment par mois actif.
#   L'allocation d'un paiement se fait À L'INTÉRIEUR d'une dette (FIFO intra-dette),
#   jamais en travers des familles.

from decimal import Decimal as _D
from datetime import date as _date

from django.db.models import Sum as _Sum


class FeeDebtKind(models.TextChoices):
    TUITION      = 'tuition',      _('Scolarité')
    ONE_TIME     = 'one_time',     _('Frais ponctuel')
    SUBSCRIPTION = 'subscription', _('Abonnement')


class DebtStatus(models.TextChoices):
    """Statut de paiement calculé (jamais stocké) — partagé dette / tranche."""
    PAID    = 'paid',    _('Payé')
    PARTIAL = 'partial', _('Partiel')
    UNPAID  = 'unpaid',  _('Impayé')


class StudentFeeAccount(models.Model):
    """
    Fiche financière d'un élève pour UNE année scolaire.

    Ancrage annuel : OneToOne vers StudentEnrollment (= élève × année × école).
    Régénérée à chaque réinscription → l'année N+1 a sa propre fiche, l'historique
    des années passées reste intact (un account par enrollment).

    Ne stocke aucun montant : total_due / total_paid / total_balance agrègent les
    trois familles de dettes à la volée.
    """
    enrollment = models.OneToOneField(
        'students.StudentEnrollment', on_delete=models.CASCADE,
        related_name='fee_account', verbose_name=_('inscription'),
    )
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('fiche financière')
        verbose_name_plural = _('fiches financières')

    def __str__(self):
        return f'Fiche financière — {self.enrollment}'

    # ── Agrégats (calculés, jamais stockés) ───────────────────────────────────
    def active_debts(self):
        return self.debts.filter(is_active=True)

    def total_due(self):
        return sum((d.total_amount for d in self.active_debts()), _D('0'))

    def total_adjustments(self):
        return sum((d.adjustments_total() for d in self.active_debts()), _D('0'))

    def total_paid(self):
        return sum((d.amount_paid() for d in self.active_debts()), _D('0'))

    def total_balance(self):
        return self.total_due() - self.total_adjustments() - self.total_paid()


class FeeDebt(models.Model):
    """
    Une dette individuelle d'un élève pour l'année. Le champ `kind` la range dans
    l'une des trois familles (jamais fondues).

    total_amount est un SNAPSHOT figé à la création (le tarif catalogue / la scolarité
    de la classe peut changer ensuite sans réécrire l'historique).
    """
    account = models.ForeignKey(
        StudentFeeAccount, on_delete=models.CASCADE,
        related_name='debts', verbose_name=_('fiche'),
    )
    # Nullable pour la scolarité (vient de la classe, pas d'un FeeType à montant).
    fee_type = models.ForeignKey(
        FeeType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='debts', verbose_name=_('type de frais'),
    )
    # Variante choisie (trajet de bus, tenue genrée…), si applicable.
    variant = models.ForeignKey(
        FeeVariant, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='debts', verbose_name=_('variante'),
    )
    kind = models.CharField(
        _('famille'), max_length=20, choices=FeeDebtKind.choices,
    )
    # Libellé figé à la création (ex. « Scolarité », « Inscription », « Bus — Kati »).
    label = models.CharField(_('libellé'), max_length=150)
    # Montant TOTAL dû pour cette dette (snapshot). Scolarité = annual_fee de la classe.
    total_amount = models.DecimalField(
        _('montant total (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    # Résiliation d'un abonnement : is_active=False → on arrête de générer ses
    # mensualités (les tranches déjà émises et payées restent).
    is_active = models.BooleanField(_('active'), default=True)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('dette')
        verbose_name_plural = _('dettes')
        ordering = ['kind', 'created_at']
        indexes = [
            models.Index(fields=['account', 'kind'], name='feedebt_account_kind_idx'),
        ]

    def __str__(self):
        return f'{self.label} — {self.total_amount} FCFA'

    # ── Agrégats (calculés) ────────────────────────────────────────────────────
    def amount_paid(self):
        """Somme des allocations vers les tranches de cette dette (1 requête)."""
        total = (
            PaymentAllocation.objects
            .filter(installment__debt=self)
            .aggregate(s=_Sum('amount'))['s']
        )
        return total or _D('0')

    def adjustments_total(self):
        """Σ des remises actives (non annulées) — valeurs FCFA figées à la création."""
        return sum(
            (a.resolved_amount for a in self.adjustments.all() if not a.is_cancelled),
            _D('0'),
        )

    def net_due(self):
        """Montant réellement dû = tarif officiel (snapshot INTOUCHABLE) − remises actives."""
        return self.total_amount - self.adjustments_total()

    def balance(self):
        return self.net_due() - self.amount_paid()

    def status(self):
        net  = self.net_due()
        paid = self.amount_paid()
        if net <= 0 or paid >= net:
            return DebtStatus.PAID
        if paid <= 0:
            return DebtStatus.UNPAID
        return DebtStatus.PARTIAL


class AdjustmentType(models.TextChoices):
    DISCOUNT = 'discount', _('Remise')
    # Prévus pour l'avenir (pas activés au niveau 1) : PENALTY, CORRECTION, WAIVER.


class AdjustmentMotif(models.TextChoices):
    FRATRIE  = 'fratrie',  _('Fratrie')
    STAFF    = 'staff',    _('Enfant du personnel')
    MERIT    = 'merit',    _('Bourse / mérite')
    SOCIAL   = 'social',   _('Cas social')
    RELATION = 'relation', _('Gratuité famille / relation')
    GIRL     = 'girl',     _('Scolarisation fille')
    EARLY    = 'early',    _('Paiement anticipé')
    GESTURE  = 'gesture',  _('Geste commercial')
    OTHER    = 'other',    _('Autre')


class FundingSource(models.TextChoices):
    SCHOOL   = 'school',   _('École')
    DONOR    = 'donor',    _('Donateur')
    PROMOTER = 'promoter', _('Promoteur')


class FeeAdjustment(models.Model):
    """
    Remise (abandon partiel de créance) sur UNE dette. Ce n'est PAS un paiement.

    - Le tarif officiel (FeeDebt.total_amount) n'est JAMAIS modifié.
    - resolved_amount = valeur FCFA FIGÉE à la création (comme un snapshot) : soit le
      montant fixe saisi, soit percent × total_amount. Tout le calcul de solde somme ce
      seul champ (Python ET sous-requêtes SQL) → aucun recalcul, aucun écart d'arrondi.
    - IMMUABLE : on ne modifie jamais une remise, on l'ANNULE (is_cancelled) et on recrée.
      Audit parfait (accordée par / annulée par / quand / motif / justification).
    """
    debt = models.ForeignKey(
        'FeeDebt', on_delete=models.CASCADE,
        related_name='adjustments', verbose_name=_('dette'),
    )
    type = models.CharField(
        _('type'), max_length=20, choices=AdjustmentType.choices,
        default=AdjustmentType.DISCOUNT,
    )
    motif = models.CharField(_('motif'), max_length=20, choices=AdjustmentMotif.choices)
    # Ce que le directeur a saisi : un pourcentage OU un montant fixe (jamais les deux).
    percent = models.DecimalField(
        _('pourcentage'), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    amount = models.DecimalField(
        _('montant fixe (FCFA)'), max_digits=12, decimal_places=0, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    # Valeur FCFA effective, figée à la création → source unique des calculs de solde.
    resolved_amount = models.DecimalField(
        _('montant de la remise (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    funding_source = models.CharField(
        _('financé par'), max_length=20, choices=FundingSource.choices,
        default=FundingSource.SCHOOL,
    )
    justification = models.TextField(_('justification'), blank=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fee_adjustments_created', verbose_name=_('accordée par'),
    )
    created_at = models.DateTimeField(_('accordée le'), auto_now_add=True)
    # Annulation (jamais de modification) :
    is_cancelled = models.BooleanField(_('annulée'), default=False)
    cancelled_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fee_adjustments_cancelled', verbose_name=_('annulée par'),
    )
    cancelled_at = models.DateTimeField(_('annulée le'), null=True, blank=True)

    class Meta:
        verbose_name = _('remise')
        verbose_name_plural = _('remises')
        ordering = ['-created_at']
        constraints = [
            # Exactement un des deux : pourcentage OU montant fixe.
            models.CheckConstraint(
                check=(
                    models.Q(percent__isnull=False, amount__isnull=True) |
                    models.Q(percent__isnull=True, amount__isnull=False)
                ),
                name='adjustment_percent_xor_amount',
            ),
        ]
        indexes = [
            models.Index(fields=['debt', 'is_cancelled'], name='adjustment_debt_idx'),
        ]

    @property
    def is_active(self):
        return not self.is_cancelled

    def __str__(self):
        return f'{self.get_motif_display()} −{self.resolved_amount} FCFA'


class Installment(models.Model):
    """
    Une échéance datée d'une dette. due_date EST le cœur de la dimension temporelle.

    - TUITION      : N tranches générées par le gabarit (dates dérivées des Period).
    - ONE_TIME     : 1 tranche (due_date = rentrée).
    - SUBSCRIPTION : 1 tranche par mois actif (générée au fil de l'année).
    """
    debt = models.ForeignKey(
        FeeDebt, on_delete=models.CASCADE,
        related_name='installments', verbose_name=_('dette'),
    )
    sequence = models.PositiveSmallIntegerField(_('ordre'), default=1)
    amount_due = models.DecimalField(
        _('montant attendu (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    due_date = models.DateField(_('date limite'))
    label = models.CharField(_('libellé'), max_length=100)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('tranche')
        verbose_name_plural = _('tranches')
        ordering = ['debt', 'sequence']
        constraints = [
            models.UniqueConstraint(
                fields=['debt', 'sequence'], name='uniq_installment_debt_sequence',
            ),
        ]
        indexes = [
            models.Index(fields=['due_date'], name='installment_due_date_idx'),
        ]

    def __str__(self):
        return f'{self.label} — {self.amount_due} FCFA (éch. {self.due_date})'

    # ── Agrégats (calculés) ────────────────────────────────────────────────────
    def amount_allocated(self):
        total = self.allocations.aggregate(s=_Sum('amount'))['s']
        return total or _D('0')

    def balance(self):
        return self.amount_due - self.amount_allocated()

    def status(self):
        alloc = self.amount_allocated()
        if alloc <= 0:
            return DebtStatus.UNPAID
        if alloc >= self.amount_due:
            return DebtStatus.PAID
        return DebtStatus.PARTIAL

    def is_overdue(self, today=None):
        """En retard = échéance passée ET solde restant > 0."""
        today = today or _date.today()
        return self.due_date < today and self.balance() > 0

    def days_overdue(self, today=None):
        today = today or _date.today()
        if not self.is_overdue(today):
            return 0
        return (today - self.due_date).days


class PaymentAllocation(models.Model):
    """
    Lien Payment ↔ Installment : le montant d'un paiement affecté à une tranche.

    PIÈCE MAÎTRESSE DE L'IMMUABILITÉ : c'est cette table — et elle seule — qui relie
    un Payment (journal immuable, apps.payments) à une dette. Un Payment de 30000 peut
    être ventilé en plusieurs allocations (15000 → tranche 1, 15000 → tranche 2). Le
    solde d'une tranche = Σ de ses allocations ; on ne mute JAMAIS un champ « payé ».
    """
    payment = models.ForeignKey(
        'payments.Payment', on_delete=models.PROTECT,
        related_name='allocations', verbose_name=_('paiement'),
    )
    installment = models.ForeignKey(
        Installment, on_delete=models.PROTECT,
        related_name='allocations', verbose_name=_('tranche'),
    )
    amount = models.DecimalField(
        _('montant affecté (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('allocation de paiement')
        verbose_name_plural = _('allocations de paiement')
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0), name='paymentallocation_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['payment'],     name='alloc_payment_idx'),
            models.Index(fields=['installment'], name='alloc_installment_idx'),
        ]

    def __str__(self):
        return f'{self.amount} FCFA : paiement #{self.payment_id} → tranche #{self.installment_id}'
