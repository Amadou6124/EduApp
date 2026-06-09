from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _


class EducationLevel(models.TextChoices):
    PRIMARY = 'primary', _('Primaire')
    MIDDLE_SCHOOL = 'middle', _('Collège')
    HIGH_SCHOOL = 'high', _('Lycée')
    UNIVERSITY = 'university', _('Université')


class School(models.Model):
    name = models.CharField(_('nom de l\'école'), max_length=200)
    city = models.CharField(_('ville'), max_length=100)
    country = models.CharField(_('pays'), max_length=100, default='Côte d\'Ivoire')
    phone_number = models.CharField(_('téléphone'), max_length=20, blank=True)
    email = models.EmailField(_('email'), blank=True)
    logo = models.ImageField(_('logo'), upload_to='schools/logos/', blank=True)
    is_active = models.BooleanField(_('active'), default=True)
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

    class Meta:
        verbose_name = _('classe')
        verbose_name_plural = _('classes')
        ordering = ['level', 'name']
        # Une classe par nom dans la même école
        unique_together = [('school', 'name')]

    def __str__(self):
        return f'{self.name} — {self.school.name}'

    def get_student_count(self):
        return self.students.filter(is_active=True).count()

    def is_full(self):
        if self.max_capacity is None:
            return False
        return self.get_student_count() >= self.max_capacity
