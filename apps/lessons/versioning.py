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


# ── Phase 2 : régénération ciblée d'UN bloc via l'IA ──────────────────────────

REGEN_BLOCKS = ('noyau', 'lecture', 'histoire')


def regenerate_block(lesson, block, source=None):
    """Régénère UN seul bloc via l'IA et l'écrit dans le BROUILLON (sans publier).

    Granularité (contrainte du pipeline) :
      - 'noyau'    → concepts + exam (+ color/guide)  [un seul appel IA]
      - 'lecture'  → reading
      - 'histoire' → story  (réutilise guide + concepts courants du brouillon)

    source : portion de document (str OU blocs image) ; si None, ré-extraite depuis
    l'unité. N'écrit QUE dans le brouillon → le prof valide ensuite (publish_draft).
    Le coût IA est additionné sur la leçon (et l'unité). Retourne le brouillon.
    """
    from decimal import Decimal
    from . import services

    if block not in REGEN_BLOCKS:
        raise ValueError(f'Bloc inconnu : {block!r}')

    meta = services._lesson_meta(lesson)
    if source is None:
        unit = lesson.unit
        if not (unit and unit.source_file):
            raise ValueError('Source indisponible pour régénérer ce bloc.')
        source = services.extract_content_from_file(unit.source_file.path, unit.source_type)

    draft = open_draft(lesson)   # garantit un espace de travail (copie de la live)
    costs = []

    if block == 'noyau':
        noyau = services.call_noyau(meta['title'], meta['summary'], source, cost_sink=costs)
        edit_draft(
            lesson,
            concepts_data=noyau['concepts'], exam_data=noyau['exam'],
            color=noyau.get('color', ''), guide=noyau.get('guide', ''),
        )
    elif block == 'lecture':
        lect = services.call_lecture(
            meta['title'], meta['summary'], source,
            meta.get('direction', 'ltr'), cost_sink=costs,
        )
        edit_draft(lesson, reading_data=lect['reading'])
    else:  # histoire — s'appuie sur les concepts/guide courants
        hist = services.call_histoire(
            meta['title'], meta['summary'], source,
            guide=(draft.guide or ''), concepts=(draft.concepts_data or []),
            cost_sink=costs,
        )
        edit_draft(lesson, story_data=hist['story'])

    total = sum(costs)
    if total:
        lesson.generation_cost_usd = (lesson.generation_cost_usd or Decimal('0')) + total
        lesson.save(update_fields=['generation_cost_usd', 'updated_at'])
        unit = lesson.unit
        if unit:
            unit.generation_cost_usd = (unit.generation_cost_usd or Decimal('0')) + total
            unit.save(update_fields=['generation_cost_usd', 'updated_at'])

    return open_draft(lesson)
