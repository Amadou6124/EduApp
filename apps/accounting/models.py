from datetime import date
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.payments.models import PaymentMethod  # réutilisation (dépendance accounting→payments)


# ─── Profil employé ──────────────────────────────────────────────────────────

class EmploymentType(models.TextChoices):
    PERMANENT = 'permanent', _('Permanent (salaire fixe)')
    VACATAIRE = 'vacataire', _("Vacataire (à l'heure)")


class EmployeeProfile(models.Model):
    """Termes d'emploi d'un membre, par école (via Membership). Isolation : membership__school."""
    membership = models.OneToOneField(
        'accounts.Membership', on_delete=models.PROTECT,
        related_name='employee_profile', verbose_name=_('appartenance'),
    )
    employment_type = models.CharField(
        _("type d'emploi"), max_length=20,
        choices=EmploymentType.choices, default=EmploymentType.PERMANENT,
    )
    monthly_salary = models.DecimalField(
        _('salaire mensuel (FCFA)'), max_digits=12, decimal_places=0,
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text=_('Pour les permanents'),
    )
    hourly_rate = models.DecimalField(
        _('taux horaire (FCFA)'), max_digits=12, decimal_places=0,
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text=_('Pour les vacataires'),
    )
    hire_date  = models.DateField(_("date d'embauche"), null=True, blank=True)
    is_active  = models.BooleanField(_('actif'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('profil employé')
        verbose_name_plural = _('profils employés')

    def __str__(self):
        return f'{self.membership.user.full_name} — {self.get_employment_type_display()}'


# ─── Tarifs vacataire par matière ────────────────────────────────────────────

class VacataireRate(models.Model):
    """Tarif horaire d'un vacataire pour un COURS précis (matière + classe).

    La paie d'un vacataire = Σ (heures émargées du cours × ce tarif). Le tarif
    peut varier selon la classe/le niveau (Maths 6ème ≠ Maths 3ème) ; les heures
    viennent de l'émargement. Isolation : profile.membership.school.
    """
    profile = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE,
        related_name='course_rates', verbose_name=_('profil employé'),
    )
    class_subject = models.ForeignKey(
        'schools.ClassSubject', on_delete=models.CASCADE,
        related_name='vacataire_rates', verbose_name=_('cours'),
    )
    hourly_rate = models.DecimalField(
        _('taux horaire (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('tarif vacataire')
        verbose_name_plural = _('tarifs vacataire')
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'class_subject'], name='uniq_vacataire_rate_course',
            ),
        ]

    def __str__(self):
        return f'{self.profile_id} — cours {self.class_subject_id} — {self.hourly_rate}/h'


# ─── Émargement enseignant (SÉPARÉ de Attendance élèves) ─────────────────────

class TeacherAttendanceStatus(models.TextChoices):
    PRESENT  = 'present',  _('Présent (cours assuré)')
    ABSENT   = 'absent',   _('Absent (cours non assuré)')
    REPLACED = 'replaced', _('Remplacé')


class SessionType(models.TextChoices):
    MORNING   = 'morning',   _('Matin')
    AFTERNOON = 'afternoon', _('Après-midi')
    FULL_DAY  = 'full',      _('Journée entière')


class TeacherAttendance(models.Model):
    """
    Émargement d'un cours. Anti-fraude : recorded_by ≠ teacher (vérifié en vue).
    Un seul émargement par (class_subject, date).
    Paie : 'present' → heures au teacher ; 'replaced' → heures au substitute ; 'absent' → personne.
    """
    teacher = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='teaching_attendances', verbose_name=_('enseignant'),
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='teacher_attendances', verbose_name=_('école'),
    )
    class_subject = models.ForeignKey(
        'schools.ClassSubject', on_delete=models.PROTECT,
        related_name='teacher_attendances', verbose_name=_('cours'),
    )
    date    = models.DateField(_('date'))
    session = models.CharField(
        _('session'), max_length=10,
        choices=SessionType.choices, default=SessionType.MORNING,
    )
    status = models.CharField(
        _('statut'), max_length=10,
        choices=TeacherAttendanceStatus.choices,
        default=TeacherAttendanceStatus.PRESENT,
    )
    substitute = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='substitute_attendances', verbose_name=_('remplaçant'),
    )
    signed_at   = models.DateTimeField(_('émargé le'), auto_now_add=True)
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='recorded_teacher_attendances', verbose_name=_('enregistré par'),
    )
    note = models.CharField(_('note'), max_length=200, blank=True)

    class Meta:
        verbose_name = _('émargement enseignant')
        verbose_name_plural = _('émargements enseignants')
        ordering = ['-date', 'class_subject']
        constraints = [
            models.UniqueConstraint(
                fields=['class_subject', 'date', 'session'],
                name='uniq_tatt_course_date_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'date'],     name='tatt_school_date_idx'),
            models.Index(fields=['teacher', 'date'],    name='tatt_teacher_date_idx'),
            models.Index(fields=['substitute', 'date'], name='tatt_sub_date_idx'),
        ]

    def __str__(self):
        return f'{self.teacher.full_name} — {self.class_subject} — {self.date} ({self.get_status_display()})'


# ─── Dépenses ────────────────────────────────────────────────────────────────

class ExpenseCategory(models.Model):
    """Catégorie de dépense. school=NULL → catégorie globale prédéfinie."""
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, null=True, blank=True,
        related_name='expense_categories', verbose_name=_('école'),
    )
    name       = models.CharField(_('nom'), max_length=100)
    icon       = models.CharField(_('icône Lucide'), max_length=40, blank=True)
    is_default = models.BooleanField(_('prédéfinie'), default=False)
    is_active  = models.BooleanField(_('active'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('catégorie de dépense')
        verbose_name_plural = _('catégories de dépense')
        ordering = ['name']

    def __str__(self):
        return self.name


class Expense(models.Model):
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='expenses', verbose_name=_('école'),
    )
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT,
        related_name='expenses', verbose_name=_('catégorie'),
    )
    amount = models.DecimalField(
        _('montant (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(1)],
    )
    date           = models.DateField(_('date'), default=date.today)
    description    = models.CharField(_('description'), max_length=300, blank=True)
    payment_method = models.CharField(
        _('mode de paiement'), max_length=20,
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    paid_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='recorded_expenses', verbose_name=_('enregistré par'),
    )
    is_cancelled = models.BooleanField(_('annulée'), default=False)
    cancelled_at = models.DateTimeField(_('annulée le'), null=True, blank=True)
    cancelled_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cancelled_expenses', verbose_name=_('annulée par'),
    )
    cancellation_reason = models.TextField(_('motif d\'annulation'), blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('dépense')
        verbose_name_plural = _('dépenses')
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['school', 'date'], name='expense_school_date_idx'),
        ]

    def __str__(self):
        return f'{self.category.name} — {self.amount} FCFA — {self.date}'


# ─── Paie ────────────────────────────────────────────────────────────────────

class SalaryStatus(models.TextChoices):
    PENDING = 'pending', _('En attente')
    PAID    = 'paid',    _('Payé')


class SalaryPayment(models.Model):
    """Versement de paie pour un mois calendaire. Snapshots immuables (anti-fraude)."""
    employee = models.ForeignKey(
        'accounts.Membership', on_delete=models.PROTECT,
        related_name='salary_payments', verbose_name=_('employé'),
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='salary_payments', verbose_name=_('école'),
    )
    year  = models.PositiveSmallIntegerField(_('année'))
    month = models.PositiveSmallIntegerField(
        _('mois'), validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    amount = models.DecimalField(
        _('montant (FCFA)'), max_digits=12, decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    # Vacataires — snapshots figés au paiement
    hours = models.DecimalField(
        _('heures'), max_digits=6, decimal_places=1, null=True, blank=True,
    )
    hourly_rate = models.DecimalField(
        _('taux horaire (FCFA)'), max_digits=12, decimal_places=0, null=True, blank=True,
    )
    status = models.CharField(
        _('statut'), max_length=10,
        choices=SalaryStatus.choices, default=SalaryStatus.PENDING,
    )
    payment_method = models.CharField(
        _('mode de paiement'), max_length=20,
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    paid_at = models.DateTimeField(_('payé le'), null=True, blank=True)
    paid_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_salaries', verbose_name=_('payé par'),
    )
    employee_name = models.CharField(_('nom employé (snapshot)'), max_length=150, blank=True)
    is_cancelled  = models.BooleanField(_('annulé'), default=False)
    cancelled_at  = models.DateTimeField(_('annulé le'), null=True, blank=True)
    cancelled_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cancelled_salaries', verbose_name=_('annulé par'),
    )
    cancellation_reason = models.TextField(_('motif d\'annulation'), blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('paie')
        verbose_name_plural = _('paies')
        ordering = ['-year', '-month', 'employee_name']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'year', 'month'],
                condition=models.Q(is_cancelled=False),
                name='uniq_salary_employee_month',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'year', 'month'], name='salary_school_period_idx'),
            models.Index(fields=['status'], name='salary_status_idx'),
        ]

    def __str__(self):
        return f'{self.employee_name or self.employee_id} — {self.month}/{self.year} — {self.get_status_display()}'
