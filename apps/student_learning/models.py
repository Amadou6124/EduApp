from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.students.models import Student
from apps.lessons.models import Lesson


class StudentSubscription(models.Model):

    class LevelType(models.TextChoices):
        PRIMAIRE   = 'primaire',   _('Primaire')
        SECONDAIRE = 'secondaire', _('Secondaire')
        SUPERIEUR  = 'superieur',  _('Supérieur / Prépa')

    class SubscriptionType(models.TextChoices):
        FREE    = 'free',    _('Gratuit')
        PREMIUM = 'premium', _('Premium')
        PREPA   = 'prepa',   _('Prépa Examen')

    class PaymentMethod(models.TextChoices):
        ORANGE_MONEY = 'orange_money', _('Orange Money')
        MOOV         = 'moov',         _('Moov Money')
        WAVE         = 'wave',         _('Wave')
        CASH         = 'cash',         _('Espèces')
        OTHER        = 'other',        _('Autre')

    PRICES_FCFA = {
        ('primaire',   'premium'): 10_000,
        ('secondaire', 'premium'): 15_000,
        ('superieur',  'premium'): 25_000,
        ('primaire',   'prepa'):   15_000,
        ('secondaire', 'prepa'):   20_000,
        ('superieur',  'prepa'):   30_000,
    }

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name=_('élève'),
    )
    level_type = models.CharField(
        _('niveau'), max_length=20,
        choices=LevelType.choices,
    )
    subscription_type = models.CharField(
        _('type'), max_length=20,
        choices=SubscriptionType.choices,
        default=SubscriptionType.FREE,
    )
    price_paid = models.DecimalField(
        _('montant payé (FCFA)'),
        max_digits=10, decimal_places=0, default=0,
    )
    start_date = models.DateField(_('début'))
    end_date = models.DateField(_('fin'))
    payment_method = models.CharField(
        _('mode paiement'), max_length=20,
        choices=PaymentMethod.choices, blank=True,
    )
    payment_reference = models.CharField(
        _('référence paiement'), max_length=100, blank=True,
    )
    is_active = models.BooleanField(_('actif'), default=True)
    activated_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='activated_subscriptions',
        verbose_name=_('activé par'),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('abonnement élève')
        verbose_name_plural = _('abonnements élèves')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'is_active'], name='sub_student_active_idx'),
            models.Index(fields=['end_date'], name='sub_end_date_idx'),
        ]

    def __str__(self):
        return (f'{self.student.full_name} — '
                f'{self.get_subscription_type_display()} '
                f'({self.start_date} → {self.end_date})')

    @property
    def is_valid(self):
        return (self.is_active and
                self.start_date <= timezone.now().date() <= self.end_date)


class LessonProgress(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='lesson_progresses',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='student_progresses',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_block_index = models.PositiveIntegerField(default=0)
    reading_time_seconds = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    notes = models.JSONField(
        default=list,
        help_text=_('Notes perso : [{block_id, text, created_at}]'),
    )
    # Bonus quiz 100% accordé une seule fois (idempotence anti-farming).
    quiz_bonus_awarded = models.BooleanField(default=False)

    class Meta:
        unique_together = [('student', 'lesson')]
        indexes = [
            models.Index(fields=['student', 'is_completed'], name='progress_student_done_idx'),
        ]


class QuizAttempt(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    quiz_id = models.CharField(max_length=20)
    question_type = models.CharField(max_length=30)
    student_answer = models.JSONField()
    is_correct = models.BooleanField()
    time_spent_seconds = models.PositiveSmallIntegerField(default=0)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'lesson'], name='quiz_student_lesson_idx'),
            models.Index(fields=['student', 'is_correct'], name='quiz_student_correct_idx'),
            models.Index(fields=['student', 'attempted_at'], name='quiz_student_date_idx'),
        ]


class StoryAttempt(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='story_attempts',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='story_attempts',
    )
    score = models.PositiveSmallIntegerField(help_text=_('% bonnes réponses'))
    answers = models.JSONField(default=list)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_at']


class Flashcard(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='flashcards',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='student_flashcards',
    )
    flashcard_id = models.CharField(max_length=20)

    # Algorithme SM-2
    ease_factor = models.DecimalField(max_digits=4, decimal_places=2, default=2.50)
    interval_days = models.PositiveSmallIntegerField(default=1)
    repetitions = models.PositiveSmallIntegerField(default=0)
    next_review_date = models.DateField(default=timezone.localdate)
    last_quality = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text=_('0-5, dernière réponse'),
    )
    total_reviews = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('student', 'lesson', 'flashcard_id')]
        indexes = [
            models.Index(fields=['student', 'next_review_date'], name='flash_student_review_idx'),
        ]


class DailyChallenge(models.Model):

    class ChallengeType(models.TextChoices):
        QUIZ_DAILY       = 'quiz_daily',       _('Quiz du jour')
        FLASHCARD_REVIEW = 'flashcard_review', _('Révision flashcards')
        LESSON_READ      = 'lesson_read',      _('Lire une leçon')
        STORY_COMPLETE   = 'story_complete',   _('Compléter une story')

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='daily_challenges',
    )
    date = models.DateField()
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='daily_challenges',
    )
    challenge_type = models.CharField(
        max_length=20, choices=ChallengeType.choices,
    )
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    xp_earned = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [('student', 'date')]
        indexes = [
            models.Index(fields=['student', 'date', 'is_completed'], name='challenge_student_date_idx'),
        ]
