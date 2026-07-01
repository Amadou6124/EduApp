from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class EducationLevel(models.TextChoices):
    PRESCOLAIRE    = 'prescolaire',    _('Préscolaire')
    FONDAMENTAL_1  = 'fondamental_1',  _('Fondamental 1er Cycle')
    FONDAMENTAL_2  = 'fondamental_2',  _('Fondamental 2ème Cycle')
    SECONDAIRE_GEN = 'secondaire_gen', _('Secondaire Général')
    SECONDAIRE_PRO = 'secondaire_pro', _('Secondaire Professionnel')
    SUPERIEUR      = 'superieur',      _('Enseignement Supérieur')


class SchoolType(models.TextChoices):
    PRIMARY    = 'primary',    _('Primaire')
    COLLEGE    = 'college',    _('Collège')
    LYCEE      = 'lycee',      _('Lycée')
    MIXED      = 'mixte',      _('Mixte (primaire + collège)')
    UNIVERSITY = 'university', _('Université')
    TRAINING   = 'formation',  _('Centre de formation')


class ReceiptMode(models.TextChoices):
    STANDARD = 'standard', _('Reçu standard EduApp')
    CUSTOM   = 'custom',   _('Reçu personnalisé')


class SchoolGroup(models.Model):
    """
    Groupe d'écoles appartenant à un même promoteur.
    Le promoteur (owner) supervise toutes les écoles du groupe ;
    chaque école conserve son propre directeur.
    """
    name = models.CharField(_('nom du groupe'), max_length=200)
    owner = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='owned_groups', verbose_name=_('promoteur'),
    )
    created_at = models.DateTimeField(_('créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('groupe scolaire')
        verbose_name_plural = _('groupes scolaires')
        ordering = ['name']

    def __str__(self):
        return self.name


class School(models.Model):
    # ── Informations générales ─────────────────────────────────────
    name         = models.CharField(_('nom de l\'école'), max_length=200)
    short_name   = models.CharField(
        _('nom court'), max_length=30, blank=True,
        help_text=_('Affiché dans la barre latérale et l\'en-tête. Ex : EPF Sundiata. '
                    'Laissé vide = le nom complet est utilisé.'),
    )
    address      = models.CharField(_('adresse'), max_length=300, blank=True)
    city         = models.CharField(_('ville'), max_length=100)
    country      = models.CharField(_('pays'), max_length=100, default='Côte d\'Ivoire')
    phone_number = models.CharField(_('téléphone'), max_length=20, blank=True)
    email        = models.EmailField(_('email'), blank=True)
    current_school_year = models.CharField(
        _('année scolaire en cours'), max_length=20, blank=True,
        help_text=_('Ex : 2024-2025'),
    )
    school_type = models.CharField(
        _('type d\'établissement'), max_length=20,
        choices=SchoolType.choices, blank=True, default='',
    )

    # ── Apparence ──────────────────────────────────────────────────
    logo = models.ImageField(_('logo'), upload_to='schools/logos/', blank=True)

    # ── Modèle de reçu ─────────────────────────────────────────────
    receipt_mode = models.CharField(
        _('mode de reçu'), max_length=10,
        choices=ReceiptMode.choices, default=ReceiptMode.STANDARD,
    )
    receipt_template_pdf = models.FileField(
        _('template reçu PDF'), upload_to='schools/receipts/', blank=True,
    )
    receipt_mapping = models.JSONField(
        _('mapping variables reçu'), default=dict, blank=True,
    )
    receipt_configured_at = models.DateTimeField(
        _('reçu configuré le'), null=True, blank=True,
    )
    receipt_signer_title = models.CharField(
        _('titre du signataire'), max_length=100,
        default='Le Caissier / Directeur', blank=True,
    )

    # ── Multi-école ────────────────────────────────────────────────
    group = models.ForeignKey(
        'schools.SchoolGroup', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='schools', verbose_name=_('groupe scolaire'),
    )

    # ── Comptabilité ───────────────────────────────────────────────
    accounting_enabled = models.BooleanField(
        _('module comptabilité activé'), default=False,
    )
    absence_deduction = models.DecimalField(
        _('retenue par absence (FCFA)'), max_digits=12, decimal_places=0,
        default=0, validators=[MinValueValidator(0)],
        help_text=_("Montant déduit du salaire d'un permanent par cours absent (0 = aucune retenue)."),
    )

    # ── Métadonnées ────────────────────────────────────────────────
    is_active  = models.BooleanField(_('active'), default=True)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('école')
        verbose_name_plural = _('écoles')
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def nav_name(self):
        """Nom affiché dans le châssis (header / sidebar) : court si défini, sinon complet."""
        return self.short_name or self.name


class SchoolClass(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='classes',
        verbose_name=_('école'),
    )
    name = models.CharField(_('nom de la classe'), max_length=100)
    level = models.CharField(
        _('niveau'),
        max_length=20,
        choices=EducationLevel.choices,
    )
    # Frais annuels en FCFA
    annual_fee = models.DecimalField(
        _('frais de scolarité annuels (FCFA)'),
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    max_capacity = models.PositiveSmallIntegerField(
        _('capacité maximale'),
        null=True,
        blank=True,
        help_text=_('Laisser vide si pas de limite'),
    )
    is_active = models.BooleanField(_('active'), default=True)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('modifiée le'), auto_now=True)
    # Délégués autorisés à saisir des notes (en plus de l'enseignant assigné)
    notes_delegates = models.ManyToManyField(
        'accounts.User',
        blank=True,
        related_name='delegate_classes',
        verbose_name=_('délégués de saisie'),
    )

    class Meta:
        verbose_name = _('classe')
        verbose_name_plural = _('classes')
        ordering = ['level', 'name']
        # Une classe par nom dans la même école (ignore les soft-deleted)
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                condition=models.Q(is_active=True),
                name='unique_active_class_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active'], name='schoolclass_school_active_idx'),
        ]

    def __str__(self):
        return f'{self.name} — {self.school.name}'

    def get_level_display_verbose(self):
        labels = {
            'prescolaire':    "Préscolaire (Jardin d'enfants)",
            'fondamental_1':  'Fondamental 1er Cycle (1ère-6ème)',
            'fondamental_2':  'Fondamental 2ème Cycle (7ème-9ème)',
            'secondaire_gen': 'Secondaire Général (Lycée/BAC)',
            'secondaire_pro': 'Secondaire Professionnel (CAP/BT)',
            'superieur':      'Enseignement Supérieur',
        }
        return labels.get(self.level, self.level)

    def get_student_count(self):
        if hasattr(self, 'student_count'):
            return self.student_count
        return self.students.filter(is_active=True).count()

    def is_full(self):
        if self.max_capacity is None:
            return False
        return self.get_student_count() >= self.max_capacity


# ──────────────────────────────────────────────────────────────
# Années scolaires + Périodes
# ──────────────────────────────────────────────────────────────

class SchoolYear(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='school_years',
        verbose_name=_('école'),
    )
    name = models.CharField(_('nom'), max_length=20)  # ex : "2024-2025"
    start_date = models.DateField(_('début'))
    end_date   = models.DateField(_('fin'))
    is_active  = models.BooleanField(_('active'), default=False)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name        = _('année scolaire')
        verbose_name_plural = _('années scolaires')
        ordering            = ['-start_date']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                condition=models.Q(is_active=True),
                name='unique_active_schoolyear_per_school',
            ),
        ]

    def clean(self):
        # Contrainte : une seule année active par école
        if self.is_active:
            qs = SchoolYear.objects.filter(school=self.school, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    _('Une seule année scolaire peut être active à la fois par école.')
                )
        # Dates cohérentes
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError(
                _('La date de fin doit être postérieure à la date de début.')
            )

    def __str__(self):
        return f'{self.name} — {self.school.name}'

    def get_periods_count(self):
        return self.periods.count()


class PeriodType(models.TextChoices):
    TRIMESTER = 'trimester', _('Trimestre')
    SEMESTER  = 'semester',  _('Semestre')
    CUSTOM    = 'custom',    _('Personnalisé')


class Period(models.Model):
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.CASCADE,
        related_name='periods',
        verbose_name=_('année scolaire'),
    )
    name        = models.CharField(_('nom'), max_length=50)  # ex : "Trimestre 1"
    period_type = models.CharField(
        _('type'),
        max_length=10,
        choices=PeriodType.choices,
        default=PeriodType.TRIMESTER,
    )
    start_date    = models.DateField(_('début'))
    end_date      = models.DateField(_('fin'))
    is_notes_open = models.BooleanField(_('saisie notes ouverte'), default=False)
    order         = models.PositiveSmallIntegerField(_('ordre'), default=1)

    class Meta:
        verbose_name        = _('période')
        verbose_name_plural = _('périodes')
        ordering            = ['order']
        unique_together     = [('school_year', 'name')]

    def __str__(self):
        return f'{self.name} — {self.school_year.name}'


# ──────────────────────────────────────────────────────────────
# Matières
# ──────────────────────────────────────────────────────────────

class Subject(models.Model):
    school     = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='subjects',
        verbose_name=_('école'),
    )
    name       = models.CharField(_('nom'), max_length=100)       # ex : "Mathématiques"
    short_name = models.CharField(_('abréviation'), max_length=10)  # ex : "Maths"
    color      = models.CharField(_('couleur'), max_length=7, default='#4F46E5')
    is_active  = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name        = _('matière')
        verbose_name_plural = _('matières')
        ordering            = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                condition=models.Q(is_active=True),
                name='unique_active_subject_per_school',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.school.name})'


class NoteSystem(models.TextChoices):
    DEVOIRS_COMPO  = 'devoirs_compo',  _('Devoirs + Composition')
    MOYENNE_SIMPLE = 'moyenne_simple', _('Moyenne simple')


class ClassSubject(models.Model):
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='class_subjects',
        verbose_name=_('classe'),
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='class_subjects',
        verbose_name=_('matière'),
    )
    coefficient = models.DecimalField(
        _('coefficient'),
        max_digits=3,
        decimal_places=1,
        default=Decimal('1.0'),
        validators=[MinValueValidator(Decimal('0.1'))],
    )
    note_system = models.CharField(
        _('système de notes'),
        max_length=20,
        choices=NoteSystem.choices,
        default=NoteSystem.MOYENNE_SIMPLE,
    )
    # Coefficients utilisés uniquement pour le mode DEVOIRS_COMPO
    coeff_devoirs = models.DecimalField(
        _('coefficient devoirs'),
        max_digits=3,
        decimal_places=2,
        default=Decimal('0.40'),
    )
    coeff_compo = models.DecimalField(
        _('coefficient composition'),
        max_digits=3,
        decimal_places=2,
        default=Decimal('0.60'),
    )
    # Note maximale : 10.00 (primaire), 20.00 (collège/lycée), 100.00 (certaines universités)
    max_grade = models.DecimalField(
        _('note maximale'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('1.00'))],
    )
    # Comptabilité : durée d'un cours (heures) pour le calcul de la paie vacataire
    duration_hours = models.DecimalField(
        _("durée d'un cours (heures)"),
        max_digits=3,
        decimal_places=1,
        default=Decimal('2.0'),
        validators=[MinValueValidator(Decimal('0.5'))],
    )
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teaching_subjects',
        verbose_name=_('enseignant'),
    )
    order     = models.PositiveSmallIntegerField(_('ordre'), default=0)
    is_active = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name        = _('matière de classe')
        verbose_name_plural = _('matières de classe')
        ordering            = ['order', 'subject__name']
        unique_together     = [('school_class', 'subject')]

    def clean(self):
        # Validation coefficients devoirs + composition = 1.0 en mode DEVOIRS_COMPO
        if self.note_system == NoteSystem.DEVOIRS_COMPO:
            total = (self.coeff_devoirs or Decimal('0')) + (self.coeff_compo or Decimal('0'))
            if abs(total - Decimal('1.00')) > Decimal('0.01'):
                raise ValidationError(
                    _('La somme des coefficients devoirs et composition doit être égale à 1.')
                )

    def __str__(self):
        return f'{self.subject.name} — {self.school_class.name}'


# ──────────────────────────────────────────────────────────────
# Notes
# ──────────────────────────────────────────────────────────────

class NoteType(models.TextChoices):
    DEVOIR      = 'devoir',      _('Devoir')
    COMPOSITION = 'composition', _('Composition')
    SIMPLE      = 'simple',      _('Note simple')


class Note(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='grade_notes',
        verbose_name=_('élève'),
    )
    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name=_('matière de classe'),
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name=_('période'),
    )
    note_type = models.CharField(
        _('type de note'),
        max_length=15,
        choices=NoteType.choices,
        default=NoteType.SIMPLE,
    )
    # Position dans la séquence : 1=première note, 2=deuxième…
    # DEVOIRS_COMPO → position 1 = devoir, position 2 = composition
    # MOYENNE_SIMPLE → position 1, 2, 3… (colonnes dynamiques)
    position = models.PositiveSmallIntegerField(_('position'), default=1)
    # La valeur ne peut jamais dépasser max_grade de la ClassSubject (validé dans clean())
    value = models.DecimalField(
        _('valeur'),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    entered_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='entered_notes',
        verbose_name=_('saisie par'),
    )
    entered_at  = models.DateTimeField(_('saisie le'), auto_now_add=True)
    modified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modified_notes',
        verbose_name=_('modifiée par'),
    )
    modified_at          = models.DateTimeField(_('modifiée le'), auto_now=True)
    is_cancelled         = models.BooleanField(_('annulée'), default=False)
    cancellation_reason  = models.TextField(_('motif d\'annulation'), blank=True)

    class Meta:
        verbose_name        = _('note')
        verbose_name_plural = _('notes')
        ordering            = ['student__full_name', 'position']
        unique_together     = [('student', 'class_subject', 'period', 'position')]
        indexes = [
            models.Index(fields=['student', 'period'],       name='note_student_period_idx'),
            models.Index(fields=['class_subject', 'period'], name='note_cs_period_idx'),
        ]

    def clean(self):
        # La note ne peut pas dépasser le maximum défini sur la matière de classe
        if self.value is not None and self.class_subject_id:
            try:
                max_grade = self.class_subject.max_grade
            except ClassSubject.DoesNotExist:
                return
            if self.value > max_grade:
                raise ValidationError({
                    'value': _(
                        f'La note ({self.value}) dépasse le maximum autorisé ({max_grade}).'
                    )
                })

    def __str__(self):
        return (
            f'{self.student} — {self.class_subject.subject.name} : '
            f'{self.value}/{self.class_subject.max_grade}'
        )


class EvaluationColumn(models.Model):
    """Nom d'une colonne d'évaluation (mode moyenne simple) — ex. « Devoir 1 », « Interro ».

    Une entrée par (matière de classe, période, position). Optionnelle : sans entrée,
    la colonne affiche un nom par défaut « Éval N ». En mode devoir/composition, les
    noms sont fixes (« Devoir » / « Composition ») et ce modèle n'est pas utilisé.
    """
    class_subject = models.ForeignKey(
        ClassSubject, on_delete=models.CASCADE,
        related_name='evaluation_columns', verbose_name=_('matière de classe'),
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE,
        related_name='evaluation_columns', verbose_name=_('période'),
    )
    position = models.PositiveSmallIntegerField(_('position'))
    name     = models.CharField(_('nom'), max_length=40)

    class Meta:
        verbose_name        = _('colonne d\'évaluation')
        verbose_name_plural = _('colonnes d\'évaluation')
        ordering            = ['position']
        constraints = [
            models.UniqueConstraint(
                fields=['class_subject', 'period', 'position'],
                name='uniq_eval_col_cs_period_position',
            ),
        ]

    def __str__(self):
        return f'{self.class_subject} — {self.period} · pos {self.position} : {self.name}'


# ──────────────────────────────────────────────────────────────
# Flux formatif (hors bulletin) — suivi entre les compositions
# ──────────────────────────────────────────────────────────────

class FormativeEvalType(models.TextChoices):
    INTERRO_ECRITE = 'interro_ecrite', _('Interrogation écrite')
    INTERRO_ORALE  = 'interro_orale',  _('Interrogation orale')
    DEVOIR_MAISON  = 'devoir_maison',  _('Devoir maison')
    AUTRE          = 'autre',          _('Autre')


class FormativeEvaluation(models.Model):
    """Évaluation formative (interro, DM, oral…) saisie par l'enseignant pour suivre
    l'état de la classe ENTRE les compositions. Ne compte JAMAIS sur le bulletin
    officiel. Le directeur peut la publier au parent (point d'étape)."""
    class_subject = models.ForeignKey(
        ClassSubject, on_delete=models.CASCADE,
        related_name='formative_evaluations', verbose_name=_('matière de classe'),
    )
    period = models.ForeignKey(
        Period, on_delete=models.CASCADE,
        related_name='formative_evaluations', verbose_name=_('période'),
    )
    date      = models.DateField(_('date'))
    eval_type = models.CharField(
        _('type'), max_length=20,
        choices=FormativeEvalType.choices, default=FormativeEvalType.INTERRO_ECRITE,
    )
    title     = models.CharField(_('libellé'), max_length=80, blank=True)
    max_grade = models.DecimalField(
        _('note maximale'), max_digits=5, decimal_places=2,
        default=Decimal('20.00'), validators=[MinValueValidator(Decimal('1.00'))],
    )
    is_published_to_parent = models.BooleanField(_('publiée au parent'), default=False)
    published_at = models.DateTimeField(_('publiée le'), null=True, blank=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='created_formative_evaluations', verbose_name=_('créée par'),
    )
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name        = _('évaluation formative')
        verbose_name_plural = _('évaluations formatives')
        ordering            = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['class_subject', 'period'], name='formeval_cs_period_idx'),
        ]

    def __str__(self):
        return f'{self.get_eval_type_display()} — {self.class_subject} ({self.date})'


class FormativeGrade(models.Model):
    """Note d'un élève pour une évaluation formative (is_absent=True → absent)."""
    evaluation = models.ForeignKey(
        FormativeEvaluation, on_delete=models.CASCADE,
        related_name='grades', verbose_name=_('évaluation'),
    )
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE,
        related_name='formative_grades', verbose_name=_('élève'),
    )
    value = models.DecimalField(
        _('note'), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    is_absent  = models.BooleanField(_('absent'), default=False)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('modifiée le'), auto_now=True)

    class Meta:
        verbose_name        = _('note formative')
        verbose_name_plural = _('notes formatives')
        ordering            = ['student__full_name']
        constraints = [
            models.UniqueConstraint(
                fields=['evaluation', 'student'],
                name='uniq_formative_grade_eval_student',
            ),
        ]

    def __str__(self):
        return f'{self.student} — {self.evaluation} : {self.value}'


# ──────────────────────────────────────────────────────────────
# Bulletins — Étape 3/3
# ──────────────────────────────────────────────────────────────

class AppreciationScale(models.Model):
    """Barème d'appréciations par école."""
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='appreciation_scales',
        verbose_name=_('école'),
    )
    min_grade = models.DecimalField(
        _('note minimale'), max_digits=5, decimal_places=2,
        help_text=_('Seuil inférieur (inclus) pour cette appréciation.'),
    )
    label = models.CharField(_('appréciation'), max_length=50)
    order = models.PositiveSmallIntegerField(_('ordre'), default=0)

    class Meta:
        verbose_name = _('barème d\'appréciation')
        verbose_name_plural = _('barèmes d\'appréciation')
        ordering = ['-min_grade']
        unique_together = [('school', 'label')]

    def __str__(self):
        return f'{self.label} (>= {self.min_grade}) — {self.school.name}'

    @staticmethod
    def get_appreciation(school, grade):
        """Retourne l'appréciation correspondant à une note."""
        if grade is None:
            return ''
        for s in (
            AppreciationScale.objects
            .filter(school=school)
            .order_by('-min_grade')
        ):
            if grade >= s.min_grade:
                return s.label
        return ''


class BulletinFormat(models.TextChoices):
    FULL_PAGE = 'full_page',     _('Pleine page A4')
    TWO_PER_PAGE = 'two_per_page', _('Deux par page A4')


class BulletinLanguage(models.TextChoices):
    FRENCH = 'french',       _('Français')
    ARABIC = 'arabic',       _('Arabe')
    BILINGUAL = 'bilingual', _('Bilingue')


class BulletinConfig(models.Model):
    """Configuration du bulletin par école (1:1)."""
    school = models.OneToOneField(
        School,
        on_delete=models.CASCADE,
        related_name='bulletin_config',
        verbose_name=_('école'),
    )
    show_ministry_header = models.BooleanField(
        _('afficher l\'en-tête ministériel'), default=True,
    )
    ministry_line1 = models.CharField(
        _('ministère — ligne 1'), max_length=200, blank=True,
        default="MINISTERE DE L'EDUCATION NATIONALE",
    )
    ministry_line2 = models.CharField(
        _('ministère — ligne 2 (ex: Académie)'), max_length=200, blank=True, default='',
    )
    ministry_line3 = models.CharField(
        _('ministère — ligne 3 (ex: CAP)'), max_length=200, blank=True, default='',
    )
    republic_line1 = models.CharField(
        _('république — ligne 1'), max_length=200, blank=True,
        default='REPUBLIQUE DU MALI',
    )
    republic_line2 = models.CharField(
        _('république — ligne 2 (devise)'), max_length=200, blank=True,
        default='UN PEUPLE - UN BUT - UNE FOI',
    )
    bulletin_title = models.CharField(
        _('titre du bulletin'), max_length=200, blank=True,
        default='RELEVE DE NOTES',
    )
    show_logo = models.BooleanField(_('afficher le logo'), default=True)
    paper_format = models.CharField(
        _('format d\'impression'), max_length=15,
        choices=BulletinFormat.choices, default=BulletinFormat.TWO_PER_PAGE,
    )
    language = models.CharField(
        _('langue du bulletin'), max_length=10,
        choices=BulletinLanguage.choices, default=BulletinLanguage.FRENCH,
    )
    show_rank = models.BooleanField(_('afficher le classement'), default=True)
    show_class_average = models.BooleanField(
        _('afficher la moyenne de classe'), default=True,
    )
    show_first_average = models.BooleanField(
        _('afficher la moyenne du premier'), default=True,
    )
    show_appreciations = models.BooleanField(
        _('afficher les appréciations'), default=True,
    )
    show_annual_averages = models.BooleanField(
        _('afficher les moyennes des autres trimestres'), default=False,
    )
    show_last_average = models.BooleanField(
        _('afficher la moyenne du dernier'), default=False,
    )
    footer_left = models.CharField(
        _('pied gauche'), max_length=100, blank=True, default='Le Parent',
    )
    footer_right = models.CharField(
        _('pied droit'), max_length=100, blank=True, default='Le Directeur',
    )

    class Meta:
        verbose_name = _('configuration bulletin')
        verbose_name_plural = _('configurations bulletin')

    def __str__(self):
        return f'Config bulletin — {self.school.name}'


class Bulletin(models.Model):
    """Bulletin généré pour un élève sur une période."""
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='bulletins',
        verbose_name=_('élève'),
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='bulletins',
        verbose_name=_('période'),
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='bulletins',
        verbose_name=_('classe'),
    )
    generated_at = models.DateTimeField(_('généré le'), auto_now_add=True)
    generated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='generated_bulletins',
        verbose_name=_('généré par'),
    )
    is_published = models.BooleanField(_('publié'), default=False)
    published_at = models.DateTimeField(_('publié le'), null=True, blank=True)
    general_average = models.DecimalField(
        _('moyenne générale'), max_digits=5, decimal_places=2, null=True, blank=True,
    )
    rank = models.PositiveIntegerField(_('rang'), null=True, blank=True)
    class_size = models.PositiveIntegerField(
        _('effectif classe'), null=True, blank=True,
    )
    first_average = models.DecimalField(
        _('moyenne du premier'), max_digits=5, decimal_places=2, null=True, blank=True,
    )
    appreciation = models.CharField(
        _('appréciation générale'), max_length=50, blank=True,
    )
    pdf_file = models.FileField(
        _('fichier PDF'), upload_to='bulletins/%Y/%m/', null=True, blank=True,
    )
    is_cancelled = models.BooleanField(_('annulé'), default=False)

    class Meta:
        verbose_name = _('bulletin')
        verbose_name_plural = _('bulletins')
        ordering = ['-generated_at']
        unique_together = [('student', 'period')]
        indexes = [
            models.Index(fields=['school_class', 'period'], name='bul_class_period_idx'),
            models.Index(fields=['student', 'period'], name='bul_student_period_idx'),
        ]

    def __str__(self):
        return (
            f'Bulletin {self.student.full_name} — '
            f'{self.period.name} ({self.period.school_year.name})'
        )


class BulletinLine(models.Model):
    """Ligne matière dans un bulletin."""
    bulletin = models.ForeignKey(
        Bulletin,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('bulletin'),
    )
    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.CASCADE,
        related_name='bulletin_lines',
        verbose_name=_('matière de classe'),
    )
    devoir_average = models.DecimalField(
        _('moyenne devoirs'), max_digits=5, decimal_places=2, null=True, blank=True,
    )
    compo_grade = models.DecimalField(
        _('note composition'), max_digits=5, decimal_places=2, null=True, blank=True,
    )
    final_average = models.DecimalField(
        _('moyenne finale matière'), max_digits=5, decimal_places=2, null=True, blank=True,
    )
    weighted_grade = models.DecimalField(
        _('note pondérée (x coefficient)'), max_digits=6, decimal_places=2,
        null=True, blank=True,
    )
    appreciation = models.CharField(
        _('appréciation matière'), max_length=50, blank=True,
    )
    rank_in_subject = models.PositiveIntegerField(
        _('rang dans la matière'), null=True, blank=True,
    )

    class Meta:
        verbose_name = _('ligne de bulletin')
        verbose_name_plural = _('lignes de bulletin')
        ordering = ['class_subject__order', 'class_subject__subject__name']

    def __str__(self):
        return f'{self.class_subject.subject.name} — {self.bulletin.student.full_name}'


# ─────────────────────────────────────────────────────────────────────
# ANNONCES ÉCOLE
# ─────────────────────────────────────────────────────────────────────

class AnnouncementAudience(models.TextChoices):
    SCHOOL  = 'school',  _("Tous les parents de l'école")
    CLASS   = 'class',   _("Parents d'une classe")
    STUDENT = 'student', _("Parent d'un élève spécifique")


class SchoolAnnouncement(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE,
        related_name='announcements', verbose_name=_('école'),
    )
    author = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='authored_announcements', verbose_name=_('auteur'),
    )
    title = models.CharField(_('titre'), max_length=200)
    body  = models.TextField(_('contenu'))
    audience = models.CharField(
        _('audience'), max_length=10,
        choices=AnnouncementAudience.choices,
        default=AnnouncementAudience.SCHOOL,
    )
    target_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='announcements', verbose_name=_('classe ciblée'),
    )
    target_student = models.ForeignKey(
        'students.Student', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='announcements', verbose_name=_('élève ciblé'),
    )
    is_published = models.BooleanField(_('publiée'), default=False)
    published_at = models.DateTimeField(_('publiée le'), null=True, blank=True)
    created_at   = models.DateTimeField(_('créée le'), auto_now_add=True)
    updated_at   = models.DateTimeField(_('modifiée le'), auto_now=True)

    class Meta:
        verbose_name = _('annonce')
        verbose_name_plural = _('annonces')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.school.name})'