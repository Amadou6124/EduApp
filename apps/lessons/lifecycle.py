"""Cycle de vie d'une leçon — Phase 4 : retrait, archivage, suppression.

Règle dure : on n'efface JAMAIS ce qu'un élève a déjà appris. Une leçon déjà
utilisée ne se supprime pas — elle s'ARCHIVE (versions + tentatives conservées).
"""
from django.db import transaction
from django.utils import timezone

from .models import Lesson, LessonContentVersion, LessonDeployment
from apps.student_learning.models import (
    LessonProgress, QuizAttempt, StoryAttempt, ExamAttempt, ConceptProgress, QuestionDraw,
)

# Modèles de progression « réelle » (tirages éphémères QuestionDraw exclus).
_ACTIVITY_MODELS = (QuizAttempt, ExamAttempt, ConceptProgress, StoryAttempt, LessonProgress)


def undeploy_all(lesson) -> int:
    """Retire la leçon de TOUTES ses classes (réversible). Retourne le nb désactivés."""
    return (LessonDeployment.objects
            .filter(lesson=lesson, is_active=True)
            .update(is_active=False))


def has_student_activity(lesson) -> bool:
    """True si un élève a déjà travaillé sur la leçon (progression/tentatives réelles)."""
    return any(m.objects.filter(lesson=lesson).exists() for m in _ACTIVITY_MODELS)


@transaction.atomic
def archive_lesson(lesson):
    """Soft-delete : sort de la bibliothèque + dépublie partout, GARDE tout
    (versions, tentatives, progression). Réversible."""
    undeploy_all(lesson)
    lesson.is_archived = True
    lesson.archived_at = timezone.now()
    lesson.save(update_fields=['is_archived', 'archived_at', 'updated_at'])
    return lesson


@transaction.atomic
def unarchive_lesson(lesson):
    lesson.is_archived = False
    lesson.archived_at = None
    lesson.save(update_fields=['is_archived', 'archived_at', 'updated_at'])
    return lesson


@transaction.atomic
def delete_lesson(lesson):
    """Suppression RÉELLE. Interdite si un élève a déjà travaillé dessus (lève
    ValueError → l'appelant doit archiver). Nettoie brouillon, tirages éphémères,
    versions puis déploiements."""
    if has_student_activity(lesson):
        raise ValueError('Leçon déjà utilisée par des élèves : archiver au lieu de supprimer.')
    # Détacher le live, purger les tirages éphémères (QuestionDraw en PROTECT), puis
    # les versions — sinon LessonContentVersion.lesson (PROTECT) bloquerait la leçon.
    lesson.active_content_version = None
    lesson.save(update_fields=['active_content_version', 'updated_at'])
    QuestionDraw.objects.filter(content_version__lesson=lesson).delete()
    LessonContentVersion.objects.filter(lesson=lesson).delete()
    lesson.delete()   # cascade : brouillon + déploiements


def remove_lesson(lesson) -> str:
    """Choisit automatiquement : 'deleted' si jamais utilisée, 'archived' sinon."""
    if has_student_activity(lesson):
        archive_lesson(lesson)
        return 'archived'
    delete_lesson(lesson)
    return 'deleted'
