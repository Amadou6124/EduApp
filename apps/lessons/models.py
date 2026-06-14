from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.schools.models import School, SchoolClass, EducationLevel
from apps.accounts.models import User


class SubjectType(models.TextChoices):
    LITERARY   = 'literary',   _('Littéraire')
    SCIENTIFIC = 'scientific', _('Scientifique')
    MATH       = 'math',       _('Mathématiques')
    LANGUAGE   = 'language',   _('Langue')
    CODE       = 'code',       _('Informatique')
    ACCOUNTING = 'accounting', _('Comptabilité')
    GEOGRAPHY  = 'geography',  _('Géographie/Histoire')
    OTHER      = 'other',      _('Autre')


class LessonStatus(models.TextChoices):
    DRAFT      = 'draft',      _('Brouillon')
    PROCESSING = 'processing', _('En cours de génération')
    READY      = 'ready',      _('Prête')
    ERROR      = 'error',      _('Erreur')


class AIProvider(models.TextChoices):
    CLAUDE = 'claude', _('Claude (Anthropic)')
    GEMINI = 'gemini', _('Gemini (Google)')


class Lesson(models.Model):
    teacher = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='lessons',
        verbose_name=_('enseignant'),
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE,
        related_name='lessons',
        verbose_name=_('école'),
        null=True, blank=True,
    )
    title = models.CharField(_('titre'), max_length=200)
    subject = models.CharField(
        _('matière'), max_length=100,
        help_text=_('Ex: Mathématiques, SVT, Français'),
    )
    subject_type = models.CharField(
        _('type de matière'), max_length=20,
        choices=SubjectType.choices,
        default=SubjectType.OTHER,
    )
    level = models.CharField(
        _('niveau'), max_length=30,
        choices=EducationLevel.choices,
        default=EducationLevel.FONDAMENTAL_1,
    )
    level_detail = models.CharField(
        _('détail niveau'), max_length=50, blank=True,
        help_text=_('Ex: 6ème Année, Terminale A'),
    )
    language = models.CharField(_('langue'), max_length=5, default='fr')

    # Fichier source uploadé
    source_file = models.FileField(
        _('fichier source'),
        upload_to='lessons/sources/%Y/%m/',
        null=True, blank=True,
    )
    source_type = models.CharField(
        _('type source'), max_length=10,
        choices=[('pdf', 'PDF'), ('image', 'Image'), ('text', 'Texte')],
        default='pdf',
    )

    # Contenu généré par IA (JSON)
    structured_content = models.JSONField(
        _('contenu structuré'), null=True, blank=True,
        help_text=_('Blocs de leçon générés par IA'),
    )
    quiz_data = models.JSONField(
        _('quiz'), null=True, blank=True,
        help_text=_('Quiz générés par IA'),
    )
    story_data = models.JSONField(
        _('story'), null=True, blank=True,
        help_text=_('Session de compréhension'),
    )
    flashcards_data = models.JSONField(
        _('flashcards'), null=True, blank=True,
        help_text=_('Flashcards pour répétition espacée'),
    )

    # Statut et métadonnées IA
    status = models.CharField(
        _('statut'), max_length=20,
        choices=LessonStatus.choices,
        default=LessonStatus.DRAFT,
    )
    processing_error = models.TextField(_('erreur'), blank=True)
    ai_provider_used = models.CharField(
        _('IA utilisée'), max_length=20,
        choices=AIProvider.choices, blank=True,
    )
    generation_cost_usd = models.DecimalField(
        _('coût génération USD'),
        max_digits=8, decimal_places=6, default=0,
    )
    generation_attempts = models.PositiveSmallIntegerField(_('tentatives'), default=0)

    # Partage
    is_public = models.BooleanField(
        _('partagée'), default=False,
        help_text=_('Visible dans la bibliothèque'),
    )
    view_count = models.PositiveIntegerField(_('vues'), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('leçon')
        verbose_name_plural = _('leçons')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'status'], name='lesson_school_status_idx'),
            models.Index(fields=['teacher', 'status'], name='lesson_teacher_status_idx'),
            models.Index(fields=['level', 'subject_type'], name='lesson_level_type_idx'),
        ]

    def __str__(self):
        return f'{self.title} — {self.subject} ({self.level})'

    @property
    def is_ready(self):
        return self.status == LessonStatus.READY

    @property
    def quiz_count(self):
        if not self.quiz_data:
            return 0
        return len(self.quiz_data.get('quizzes', []))

    @property
    def flashcard_count(self):
        if not self.flashcards_data:
            return 0
        return len(self.flashcards_data.get('flashcards', []))


class LessonDeployment(models.Model):
    """Leçon déployée dans une classe spécifique."""
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='deployments',
        verbose_name=_('leçon'),
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE,
        related_name='lesson_deployments',
        verbose_name=_('école'),
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name='lesson_deployments',
        verbose_name=_('classe'),
        null=True, blank=True,
    )
    deployed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='lesson_deployments',
        verbose_name=_('déployée par'),
    )
    is_active = models.BooleanField(_('active'), default=True)
    deployed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('déploiement leçon')
        verbose_name_plural = _('déploiements leçons')
        unique_together = [('lesson', 'school_class')]
        indexes = [
            models.Index(fields=['school', 'is_active'], name='deploy_school_active_idx'),
        ]

    def __str__(self):
        return f'{self.lesson.title} → {self.school_class}'
