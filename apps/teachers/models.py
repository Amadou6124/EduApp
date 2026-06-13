from decimal import Decimal
from datetime import date

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class AttendanceStatus(models.TextChoices):
    PRESENT = 'present', _('Présent')
    ABSENT  = 'absent',  _('Absent')
    LATE    = 'late',    _('En retard')


class Attendance(models.Model):
    """Présence — une ligne par élève par jour par classe."""
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='attendances',
        verbose_name=_('école'),
    )
    school_class = models.ForeignKey(
        'schools.SchoolClass',
        on_delete=models.CASCADE,
        related_name='attendances',
        verbose_name=_('classe'),
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='attendances',
        verbose_name=_('élève'),
    )
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='attendances_recorded',
        verbose_name=_('enseignant'),
    )
    date   = models.DateField(_('date'))
    status = models.CharField(
        _('statut'),
        max_length=10,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    note        = models.CharField(_('note'), max_length=200, blank=True)
    recorded_at = models.DateTimeField(_('enregistré le'), auto_now_add=True)
    updated_at  = models.DateTimeField(_('modifié le'), auto_now=True)

    class Meta:
        verbose_name        = _('présence')
        verbose_name_plural = _('présences')
        ordering            = ['-date', 'student__full_name']
        constraints = [
            models.UniqueConstraint(
                fields=['school_class', 'student', 'date'],
                name='unique_attendance_per_student_date',
            ),
        ]
        indexes = [
            models.Index(
                fields=['school', 'school_class', 'date'],
                name='att_school_cls_date_idx',
            ),
            models.Index(
                fields=['student', 'date'],
                name='attendance_student_date_idx',
            ),
        ]

    def __str__(self):
        return (
            f'{self.student.full_name} — {self.date} — {self.get_status_display()}'
        )


class ObservationType(models.TextChoices):
    BEHAVIOUR = 'behaviour', _('Comportement')
    ACADEMIC  = 'academic',  _('Académique')
    HEALTH    = 'health',    _('Santé')
    OTHER     = 'other',     _('Autre')


class StudentObservation(models.Model):
    """Observation rédigée par un enseignant sur un élève."""
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='observations',
        verbose_name=_('école'),
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='observations',
        verbose_name=_('élève'),
    )
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='observations_written',
        verbose_name=_('enseignant'),
    )
    observation_type = models.CharField(
        _('type'),
        max_length=20,
        choices=ObservationType.choices,
        default=ObservationType.ACADEMIC,
    )
    content    = models.TextField(_('contenu'))
    created_at = models.DateTimeField(_('rédigée le'), auto_now_add=True)
    is_private = models.BooleanField(_('note privée'), default=True)
    # Badge "non-lu" pour notification admin (visible uniquement si is_private=False)
    is_read = models.BooleanField(_('lue par admin'), default=False)
    read_at = models.DateTimeField(_('lue le'), null=True, blank=True)
    read_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='observations_read',
        verbose_name=_('lue par'),
    )

    class Meta:
        verbose_name        = _('observation')
        verbose_name_plural = _('observations')
        ordering            = ['-created_at']
        indexes = [
            models.Index(
                fields=['school', 'is_read'],
                name='observation_school_read_idx',
            ),
            models.Index(
                fields=['student', 'teacher'],
                name='obs_student_teacher_idx',
            ),
        ]

    def __str__(self):
        return (
            f'{self.teacher.full_name} → {self.student.full_name}'
            f' ({self.get_observation_type_display()})'
        )


class QuickAssessment(models.Model):
    """
    Évaluation rapide privée — oral, contrôle, devoir maison, travail classe.
    Ne figure pas dans les bulletins officiels.
    Visible uniquement par l'enseignant qui l'a saisie.
    Utilisée pour calculer le score de difficulté de l'élève.
    """

    class AssessmentType(models.TextChoices):
        ORAL      = 'oral',      _('Interrogation orale')
        WRITTEN   = 'written',   _('Petit contrôle écrit')
        HOMEWORK  = 'homework',  _('Devoir maison')
        CLASSWORK = 'classwork', _('Travail en classe')
        BEHAVIOR  = 'behavior',  _('Comportement / Participation')

    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quick_assessments',
        verbose_name=_('enseignant'),
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='quick_assessments',
        verbose_name=_('élève'),
    )
    class_subject = models.ForeignKey(
        'schools.ClassSubject',
        on_delete=models.PROTECT,
        related_name='quick_assessments',
        verbose_name=_('matière de classe'),
    )
    period = models.ForeignKey(
        'schools.Period',
        on_delete=models.PROTECT,
        related_name='quick_assessments',
        verbose_name=_('période'),
    )
    assessment_type = models.CharField(
        _('type'),
        max_length=20,
        choices=AssessmentType.choices,
        default=AssessmentType.ORAL,
    )
    value = models.DecimalField(
        _('note obtenue'),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    max_value = models.DecimalField(
        _('note maximale'),
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('1.00'))],
    )
    note        = models.CharField(_('remarque'), max_length=200, blank=True)
    assessed_at = models.DateField(_('date'), default=date.today)
    created_at  = models.DateTimeField(_('créée le'), auto_now_add=True)

    class Meta:
        verbose_name        = _('évaluation rapide')
        verbose_name_plural = _('évaluations rapides')
        ordering            = ['-assessed_at', '-created_at']
        indexes = [
            models.Index(
                fields=['teacher', 'student', 'period'],
                name='qa_teacher_student_per_idx',
            ),
            models.Index(
                fields=['class_subject', 'period'],
                name='qa_cs_period_idx',
            ),
        ]

    def __str__(self):
        teacher_name = self.teacher.full_name if self.teacher else '(supprimé)'
        return (
            f'{teacher_name} → {self.student.full_name}'
            f' [{self.get_assessment_type_display()}] : {self.value}/{self.max_value}'
        )
