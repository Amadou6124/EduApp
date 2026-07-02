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
    PARTIAL    = 'partial',    _('Partiel')
    ERROR      = 'error',      _('Erreur')


class AIProvider(models.TextChoices):
    CLAUDE = 'claude', _('Claude (Anthropic)')
    GEMINI = 'gemini', _('Gemini (Google)')


class TextDirection(models.TextChoices):
    LTR = 'ltr', _('Gauche → droite')
    RTL = 'rtl', _('Droite → gauche (arabe)')


class Unit(models.Model):
    """Unité v2 (PORTAL_V2_SPEC) : un document source = une unité contenant
    plusieurs leçons. Porte les métadonnées document-level (source, matière,
    sens de lecture) produites par le Prompt Architecte. Additif, parallèle au v1."""
    teacher = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='units',
        verbose_name=_('enseignant'),
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE,
        related_name='units',
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
    direction = models.CharField(
        _('sens de lecture'), max_length=3,
        choices=TextDirection.choices,
        default=TextDirection.LTR,
    )

    # Fichier source uploadé (le document vit au niveau unité en v2)
    source_file = models.FileField(
        _('fichier source'),
        upload_to='units/sources/%Y/%m/',
        null=True, blank=True,
    )
    source_type = models.CharField(
        _('type source'), max_length=10,
        choices=[('pdf', 'PDF'), ('image', 'Image'), ('text', 'Texte')],
        default='pdf',
    )

    # Statut et métadonnées IA (génération de la structure par l'Architecte)
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

    # Verrou de génération (anti-double-thread) : null = aucun thread actif ;
    # une date = thread démarré / dernier heartbeat (re-tamponné après chaque leçon).
    # Expiration via GENERATION_LOCK_TIMEOUT → un thread mort ne bloque pas à jamais.
    # Acquisition par UPDATE atomique conditionnel (cf. services._acquire_generation_lock).
    generation_lock_at = models.DateTimeField(_('verrou génération'), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('unité')
        verbose_name_plural = _('unités')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.subject} ({self.level})'


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
    # v2 (PORTAL_V2_SPEC) : rattachement à l'unité (document). Nullable →
    # cohabitation v1 (unit=null). PROTECT : verrou anti-orphelinage uniforme.
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT,
        related_name='lessons',
        verbose_name=_('unité'),
        null=True, blank=True,
    )
    title = models.CharField(_('titre'), max_length=200)
    # v2 : résumé de la leçon (Architecte) + slug stable pour URLs Phase C.
    # Nullable → cohabitation v1. Pas de contrainte d'unicité base sur slug
    # pour l'instant (la PK reste l'identité ; unique_together(unit, slug) plus tard).
    summary = models.TextField(_('résumé'), null=True, blank=True)
    slug = models.SlugField(_('slug'), max_length=100, null=True, blank=True)
    # v2 : ordre de la leçon dans son unité (validation prof — réordonnancement).
    # Défaut 0 ; posé à la création du skeleton (séquence Architecte). Servira aussi
    # à ordonner les leçons dans le parcours élève. Additif, sans impact v1.
    order = models.PositiveSmallIntegerField(_('ordre'), default=0)
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

    # Versioning de format (v1 = pipeline historique ; v2 = PORTAL_V2_SPEC :
    # unité → leçon → concepts/passes, contenu versionné). Additif, cohabitation v1/v2.
    format_version = models.PositiveSmallIntegerField(
        _('version de format'), default=1,
        help_text=_('1 = format historique ; 2 = format v2 (unité/concepts/passes)'),
    )
    # v2 : pointeur vers la version de contenu LIVE (immuable). SET_NULL — un
    # pointeur "live" ne doit pas bloquer (≠ PROTECT) ; la leçon survit si on
    # dé-active. related_name='+' (pas de reverse depuis la version).
    active_content_version = models.ForeignKey(
        'LessonContentVersion', on_delete=models.SET_NULL,
        related_name='+', null=True, blank=True,
        verbose_name=_('version de contenu active'),
    )

    # Partage
    is_public = models.BooleanField(
        _('partagée'), default=False,
        help_text=_('Visible dans la bibliothèque'),
    )
    view_count = models.PositiveIntegerField(_('vues'), default=0)

    # Archivage (Phase 4) : soft-delete d'une leçon déjà utilisée (historique gardé).
    is_archived = models.BooleanField(_('archivée'), default=False)
    archived_at = models.DateTimeField(_('archivée le'), null=True, blank=True)

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


class LessonContentVersion(models.Model):
    """Version IMMUABLE du contenu pédagogique d'une leçon v2 (PORTAL_V2_SPEC).

    Append-only : régénérer = NOUVELLE version, jamais d'écrasement. La progression
    d'élève (QuizAttempt/ConceptProgress/ExamAttempt) pointe une version en PROTECT
    → jamais d'orphelinage. Le « live » est le pointeur Lesson.active_content_version."""
    lesson = models.ForeignKey(
        Lesson, on_delete=models.PROTECT,
        related_name='content_versions',
        verbose_name=_('leçon'),
    )
    version = models.PositiveSmallIntegerField(_('version'))

    # Contenu généré (B1/B2/B3), version-scopé. Null tant qu'un bloc n'est pas
    # généré (assemblage progressif) ; la complétude est vérifiée à l'activation.
    concepts_data = models.JSONField(_('concepts'), null=True, blank=True)
    reading_data = models.JSONField(_('lecture'), null=True, blank=True)
    exam_data = models.JSONField(_('examen'), null=True, blank=True)
    story_data = models.JSONField(_('histoire'), null=True, blank=True)
    # color/guide = contenu généré par B1 (version-scopé, pas identité de la leçon).
    color = models.CharField(_('couleur'), max_length=9, blank=True)
    guide = models.CharField(_('guide'), max_length=50, blank=True)

    # Provenance
    generated_at = models.DateTimeField(_('généré le'), auto_now_add=True)
    ai_provider_used = models.CharField(
        _('IA utilisée'), max_length=20,
        choices=AIProvider.choices, blank=True,
    )
    generation_cost_usd = models.DecimalField(
        _('coût génération USD'),
        max_digits=8, decimal_places=6, default=0,
    )

    # Tampon de validation (Phase 4) : qui a validé cette version, et quand.
    validated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_('validée par'),
    )
    validated_at = models.DateTimeField(_('validée le'), null=True, blank=True)

    class Meta:
        verbose_name = _('version de contenu')
        verbose_name_plural = _('versions de contenu')
        ordering = ['lesson', 'version']
        unique_together = [('lesson', 'version')]

    def __str__(self):
        return f'{self.lesson.title} — v{self.version}'


class LessonContentDraft(models.Model):
    """Espace de travail MUTABLE pour éditer / enrichir une leçon avant publication
    (Phase 1). Invisible aux élèves : seul Lesson.active_content_version est servi.

    Un seul brouillon par leçon. « Publier » le fige en une LessonContentVersion
    immuable (append-only) et bascule le live — les versions passées et la
    progression des élèves (PROTECT) ne sont jamais touchées. Éditer ne change
    RIEN pour l'élève tant qu'on n'a pas publié."""
    lesson = models.OneToOneField(
        Lesson, on_delete=models.CASCADE,
        related_name='content_draft',
        verbose_name=_('leçon'),
    )
    based_on_version = models.PositiveSmallIntegerField(
        _('forké depuis la version'), null=True, blank=True,
        help_text=_('Version live au moment de l\'ouverture du brouillon.'),
    )

    # Mêmes blocs que LessonContentVersion, mais MUTABLES.
    concepts_data = models.JSONField(_('concepts'), null=True, blank=True)
    reading_data = models.JSONField(_('lecture'), null=True, blank=True)
    exam_data = models.JSONField(_('examen'), null=True, blank=True)
    story_data = models.JSONField(_('histoire'), null=True, blank=True)
    color = models.CharField(_('couleur'), max_length=9, blank=True)
    guide = models.CharField(_('guide'), max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('brouillon de contenu')
        verbose_name_plural = _('brouillons de contenu')

    def __str__(self):
        return f'Brouillon — {self.lesson.title}'
