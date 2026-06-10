from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class EducationLevel(models.TextChoices):
    PRIMARY    = 'primary',    _('Primaire')
    MIDDLE_SCHOOL = 'middle',  _('Collège')
    HIGH_SCHOOL   = 'high',    _('Lycée')
    UNIVERSITY    = 'university', _('Université')


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


class School(models.Model):
    # ── Informations générales ─────────────────────────────────────
    name         = models.CharField(_('nom de l\'école'), max_length=200)
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
    logo          = models.ImageField(_('logo'), upload_to='schools/logos/', blank=True)
    primary_color = models.CharField(
        _('couleur principale'), max_length=7, default='#1E3A5F',
        help_text=_('Code hexadécimal, ex : #1E3A5F'),
    )

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

    # ── Métadonnées ────────────────────────────────────────────────
    is_active  = models.BooleanField(_('active'), default=True)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name = _('école')
        verbose_name_plural = _('écoles')
        ordering = ['name']

    def __str__(self):
        return self.name


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
        # Une classe par nom dans la même école
        unique_together = [('school', 'name')]

    def __str__(self):
        return f'{self.name} — {self.school.name}'

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
    name = models.CharField(_('nom'), max_length=20)  # ex : "2024-2025"
    start_date = models.DateField(_('début'))
    end_date   = models.DateField(_('fin'))
    is_active  = models.BooleanField(_('active'), default=False)
    created_at = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name        = _('année scolaire')
        verbose_name_plural = _('années scolaires')
        ordering            = ['-start_date']
        unique_together     = [('school', 'name')]

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
    name        = models.CharField(_('nom'), max_length=50)  # ex : "Trimestre 1"
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
    name       = models.CharField(_('nom'), max_length=100)       # ex : "Mathématiques"
    short_name = models.CharField(_('abréviation'), max_length=10)  # ex : "Maths"
    color      = models.CharField(_('couleur'), max_length=7, default='#1E3A5F')
    is_active  = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name        = _('matière')
        verbose_name_plural = _('matières')
        ordering            = ['name']
        unique_together     = [('school', 'name')]

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
        on_delete=models.CASCADE,
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
            f'{self.student} — {self.class_subject.subject.name} : '
            f'{self.value}/{self.class_subject.max_grade}'
        )
