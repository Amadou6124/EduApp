"""Édition versionnée du contenu des leçons v2 — Phase 1.

Brouillon MUTABLE (LessonContentDraft) pour éditer/enrichir → publication = snapshot
IMMUABLE en LessonContentVersion + bascule du live. Les versions publiées ne sont
JAMAIS mutées : la progression élève (QuizAttempt/ExamAttempt/ConceptProgress, en
PROTECT) reste intacte.

Primitives (pures, testables sans interface) :
  open_draft(lesson)          → crée/retourne le brouillon (copie de la live)
  edit_draft(lesson, **blocs) → patch au niveau bloc (crée le brouillon si besoin)
  publish_draft(lesson)       → fige en nouvelle version + bascule le live (atomique)
  discard_draft(lesson)       → jette les edits non publiés
"""
from django.db import transaction

from .models import Lesson, LessonContentVersion, LessonContentDraft

# Blocs de contenu (JSON) + métadonnées version-scopées, partagés version/brouillon.
BLOCK_FIELDS = ('concepts_data', 'reading_data', 'exam_data', 'story_data', 'color', 'guide')
_STR_FIELDS = ('color', 'guide')


def _blocks_from_version(version):
    """Dict des blocs d'une version (ou valeurs vides si aucune version live)."""
    if version is None:
        return {f: ('' if f in _STR_FIELDS else None) for f in BLOCK_FIELDS}
    return {f: getattr(version, f) for f in BLOCK_FIELDS}


def open_draft(lesson):
    """Retourne le brouillon de la leçon, en le créant depuis la version live si absent."""
    draft = LessonContentDraft.objects.filter(lesson=lesson).first()
    if draft is not None:
        return draft
    live = lesson.active_content_version
    return LessonContentDraft.objects.create(
        lesson=lesson,
        based_on_version=(live.version if live else None),
        **_blocks_from_version(live),
    )


def edit_draft(lesson, **blocks):
    """Applique un patch au niveau bloc sur le brouillon (le crée si besoin).

    Seuls les blocs fournis (parmi BLOCK_FIELDS) sont remplacés ; les autres
    restent inchangés. Ne touche jamais une version publiée."""
    allowed = {k: v for k, v in blocks.items() if k in BLOCK_FIELDS}
    with transaction.atomic():
        draft = open_draft(lesson)
        if allowed:
            for k, v in allowed.items():
                setattr(draft, k, v)
            draft.save(update_fields=list(allowed.keys()) + ['updated_at'])
    return draft


@transaction.atomic
def publish_draft(lesson):
    """Fige le brouillon en une NOUVELLE LessonContentVersion immuable, bascule le
    live, puis supprime le brouillon. Atomique + verrou sur la leçon (numéro de
    version sans collision, même en concurrence).

    Retourne la nouvelle version. Lève ValueError s'il n'y a pas de brouillon."""
    locked = Lesson.objects.select_for_update().get(pk=lesson.pk)
    draft = LessonContentDraft.objects.filter(lesson=locked).first()
    if draft is None:
        raise ValueError('Aucun brouillon à publier.')

    last = (LessonContentVersion.objects
            .filter(lesson=locked).order_by('-version').first())
    next_version = (last.version + 1) if last else 1

    version = LessonContentVersion.objects.create(
        lesson=locked,
        version=next_version,
        concepts_data=draft.concepts_data,
        reading_data=draft.reading_data,
        exam_data=draft.exam_data,
        story_data=draft.story_data,
        color=draft.color,
        guide=draft.guide,
    )
    locked.active_content_version = version
    locked.save(update_fields=['active_content_version', 'updated_at'])
    draft.delete()

    # Reflète la bascule sur l'instance passée par l'appelant.
    lesson.active_content_version = version
    return version


def discard_draft(lesson):
    """Jette le brouillon (edits non publiés). Idempotent."""
    LessonContentDraft.objects.filter(lesson=lesson).delete()
