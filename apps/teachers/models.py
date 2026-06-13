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
    # Badge "non-lu" pour notification admin (Phase 6)
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
