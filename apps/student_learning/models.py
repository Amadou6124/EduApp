from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.students.models import Student
from apps.lessons.models import Lesson, LessonContentVersion


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

    # v2 (PORTAL_V2_SPEC) : rattachement au versioning. Null pour les rows v1.
    # content_version PROTECT → étend le verrou anti-orphelinage au log de réponses.
    content_version = models.ForeignKey(
        LessonContentVersion, on_delete=models.PROTECT,
        related_name='quiz_attempts',
        null=True, blank=True,
    )
    # Snapshot des variables tirées (audit self-contained, §7.1) : rempli SEULEMENT
    # pour les quiz dynamic_formula ; null pour tous les autres types. Permet de
    # garder QuestionDraw purgeable (snapshot choisi plutôt que FK pointeur).
    draw_variables = models.JSONField(null=True, blank=True)

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

    # v2 (PORTAL_V2_SPEC) : rattachement au versioning (même pattern que QuizAttempt).
    # Null pour les complétions v1 (story_finish) → v1 inchangé. PROTECT : étend le
    # verrou anti-orphelinage de la version aux complétions de story v2.
    content_version = models.ForeignKey(
        LessonContentVersion, on_delete=models.PROTECT,
        related_name='story_attempts',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-completed_at']


# ─────────────────────────────────────────────────────────────────────────────
# v2 (PORTAL_V2_SPEC) — Progression & examen, ancrés sur LessonContentVersion.
# content_version en PROTECT = verrou anti-orphelinage (la progression d'élève
# pointe une version immuable ; on ne supprime jamais une version porteuse).
# Additif, parallèle aux modèles v1 (QuizAttempt/LessonProgress restent intacts).
# ─────────────────────────────────────────────────────────────────────────────

class ExamAttempt(models.Model):
    """Tentative d'examen v2 (§3.7). REJOUABLE : pas d'unique(student, version) —
    un élève qui échoue doit pouvoir repasser ; attempt_number croissant (serveur
    = count+1). Verdict GELÉ : pass_mark snapshoté, score, passed.

    answers = liste JSON ; chaque entrée porte PAR CONVENTION (pas de colonne
    structurelle, c'est du JSON) :
      { quiz_id, concept_id (snapshot → bilan par concept calculé à la volée),
        student_answer, is_correct, variables? (tirage dynamic_formula → audit
        self-contained) }.
    Le bilan par concept et la "meilleure/dernière" tentative sont des REQUÊTES,
    pas des champs dénormalisés."""
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='exam_attempts',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='exam_attempts',
    )
    content_version = models.ForeignKey(
        LessonContentVersion, on_delete=models.PROTECT,
        related_name='exam_attempts',
    )
    attempt_number = models.PositiveSmallIntegerField(default=1)
    pass_mark = models.FloatField(help_text=_('Seuil de réussite, gelé au moment de la tentative'))
    score = models.FloatField(default=0, help_text=_('Fraction 0..1, dérivée de answers'))
    passed = models.BooleanField(default=False)
    answers = models.JSONField(default=list)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['student', 'lesson'], name='exam_student_lesson_idx'),
            models.Index(fields=['student', 'content_version'], name='exam_student_version_idx'),
        ]


class ConceptProgress(models.Model):
    """Progression par concept/passe (v2). PROJECTION DÉNORMALISÉE : la source de
    vérité reste QuizAttempt ; la règle d'incrémentation de passes_done est de la
    logique de vue (Phase C), pas du modèle. PAS de passes_total (c'est du contenu,
    dans le JSON de la version — le dénormaliser le figerait)."""
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='concept_progresses',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='concept_progresses',
    )
    content_version = models.ForeignKey(
        LessonContentVersion, on_delete=models.PROTECT,
        related_name='concept_progresses',
    )
    concept_id = models.CharField(max_length=50)
    passes_done = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('student', 'content_version', 'concept_id')]
        indexes = [
            models.Index(fields=['student', 'lesson'], name='cprog_student_lesson_idx'),
        ]


class QuestionDraw(models.Model):
    """Tirage serve-time d'un dynamic_formula (v2). État ÉPHÉMÈRE/PRUNABLE : créé au
    serve, lu au submit ; les variables sont ensuite snapshotées dans l'enregistrement
    permanent (ExamAttempt.answers / QuizAttempt.draw_variables), donc cette table
    reste purgeable (pas de FK pointeur entrant — on a choisi le snapshot pour ça).

    variables = le context anti-triche A.5 (source serveur de confiance, JAMAIS du
    client). Réponse attendue NON stockée → recalcul via _safe_eval_arith au submit.

    Contrainte partielle uniq_exam_draw : en EXAMEN, un seul tirage par
    (exam_attempt, quiz_id) → immuable, anti-reroll (un refresh ne re-tire pas).
    En practice (exam_attempt=null), AUCUNE contrainte → re-tirage libre."""
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='question_draws',
    )
    content_version = models.ForeignKey(
        LessonContentVersion, on_delete=models.PROTECT,
        related_name='question_draws',
    )
    quiz_id = models.CharField(max_length=20)
    exam_attempt = models.ForeignKey(
        ExamAttempt, on_delete=models.CASCADE,
        related_name='question_draws',
        null=True, blank=True,
    )
    variables = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['exam_attempt', 'quiz_id'],
                condition=models.Q(exam_attempt__isnull=False),
                name='uniq_exam_draw',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'content_version', 'quiz_id'],
                         name='draw_practice_lookup_idx'),
            models.Index(fields=['exam_attempt'], name='draw_exam_attempt_idx'),
        ]


class StudentNote(models.Model):
    """Note perso de lecture prise par l'élève dans le lecteur v2 (persistée).

    Rattachée à la LEÇON (stable au fil des régénérations de contenu) pour que
    l'élève retrouve ses notes intactes ; content_version conservé pour la
    provenance (même verrou anti-orphelinage PROTECT que les autres modèles v2).
    La section est stockée en TITRE (robuste au ré-ordonnancement).
    """
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='reading_notes',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='reading_notes',
    )
    content_version = models.ForeignKey(
        LessonContentVersion, on_delete=models.PROTECT,
        related_name='reading_notes',
        null=True, blank=True,
    )
    section = models.CharField(
        max_length=200, blank=True,
        help_text=_('Titre de la section au moment de la prise'),
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'lesson'], name='note_student_lesson_idx'),
        ]
