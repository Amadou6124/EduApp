"""Contrôle qualité du contenu d'une leçon — Phase 3.

Deux niveaux, le déterministe d'abord :
  • structural_check  : vérifs pures, gratuites, JAMAIS de faux positif
    (références de concept, index de réponse hors bornes, ordre invalide, pass_mark).
  • ai_quality_check  : 2ᵉ passage IA (sémantique) — la réponse marquée est-elle
    correcte et ancrée dans la source ? Fail-safe : toute erreur IA → aucun drapeau
    (ne bloque jamais la validation).

quality_check(content, source) = union, triée (error avant warn).

Un drapeau : { block, concept_id, item_id, severity: 'error'|'warn', code, message }.
Le contenu attendu : dict { concepts: [...], exam: {...}, reading, story } — cf.
content_of() pour l'extraire d'un brouillon ou d'une version.
"""
import logging

logger = logging.getLogger(__name__)


def _flag(block, concept_id, item_id, severity, code, message):
    return {
        'block': block, 'concept_id': concept_id, 'item_id': item_id,
        'severity': severity, 'code': code, 'message': message,
    }


def content_of(obj):
    """Normalise un brouillon ou une version en dict de blocs."""
    return {
        'concepts': getattr(obj, 'concepts_data', None) or [],
        'exam':     getattr(obj, 'exam_data', None) or {},
        'reading':  getattr(obj, 'reading_data', None),
        'story':    getattr(obj, 'story_data', None),
    }


# ── 1. Déterministe (pur, testé à 100 %) ──────────────────────────────────────

def _check_quiz(q, *, block, concept_id):
    """Vérifs certaines sur un quiz/question. Conservateur : ne signale que ce qui
    est indéniablement cassé (pas de doute sémantique ici)."""
    flags = []
    if not isinstance(q, dict):
        return flags
    qid = q.get('id') or '?'

    opts = q.get('options')
    idx = q.get('answer_indices')
    if isinstance(opts, list) and isinstance(idx, list):
        n = len(opts)
        for i in idx:
            if not (isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n):
                flags.append(_flag(block, concept_id, qid, 'error', 'index_oob',
                                   f'Index de réponse hors bornes : {i} ({n} options).'))
        if not idx:
            flags.append(_flag(block, concept_id, qid, 'warn', 'no_answer',
                               'Aucune réponse correcte marquée.'))
    if isinstance(opts, list) and len(opts) == 0:
        flags.append(_flag(block, concept_id, qid, 'warn', 'empty_options',
                           'Question sans options.'))

    items = q.get('items')
    order = q.get('correct_order')
    if isinstance(items, list) and isinstance(order, list):
        if sorted(order) != list(range(len(items))):
            flags.append(_flag(block, concept_id, qid, 'error', 'bad_order',
                               "L'ordre correct n'est pas une permutation valide des éléments."))
    return flags


def structural_check(content):
    """Vérifs déterministes → liste de drapeaux. Aucun appel IA."""
    flags = []
    concepts = content.get('concepts') or []
    exam = content.get('exam') or {}

    concept_ids = {c['id'] for c in concepts if isinstance(c, dict) and c.get('id')}

    for c in concepts:
        if not isinstance(c, dict):
            continue
        for q in (c.get('quiz') or []):
            flags += _check_quiz(q, block='concepts', concept_id=c.get('id'))

    if exam:
        pm = exam.get('pass_mark')
        if pm is not None and not (isinstance(pm, (int, float)) and not isinstance(pm, bool)
                                   and 0 <= pm <= 1):
            flags.append(_flag('exam', None, 'exam', 'error', 'pass_mark',
                               f'Seuil de réussite invalide : {pm}.'))
        for q in (exam.get('questions') or []):
            if not isinstance(q, dict):
                continue
            ref = q.get('concept_id')
            if ref and ref not in concept_ids:
                flags.append(_flag('exam', ref, q.get('id') or '?', 'error', 'bad_ref',
                                   f'Question liée à un concept inexistant : {ref}.'))
            flags += _check_quiz(q, block='exam', concept_id=ref)
    return flags


# ── 2. Critique IA (sémantique, fail-safe) ────────────────────────────────────

CRITIQUE_PROMPT = """Tu es un relecteur pédagogique rigoureux. On te donne le CONTENU généré d'une
leçon (concepts, quiz, examen) et la SOURCE d'origine. Ta seule tâche : repérer les
erreurs qui feraient apprendre du FAUX à l'élève.

Pour chaque quiz/question, vérifie :
- la réponse marquée correcte l'est-elle VRAIMENT ?
- l'affirmation est-elle ANCRÉE dans la source (pas inventée) ?

Ne signale QUE les vrais problèmes (sois avare : un doute réel, pas un goût personnel).
Réponds UNIQUEMENT en JSON : { "flags": [ { "item_id": "...", "concept_id": "...",
"block": "concepts|exam", "reason": "phrase courte" } ] }. Aucun problème → {"flags": []}.

SOURCE :
{source}

CONTENU (JSON) :
{content}
"""


def call_critique(content, source):
    """Appel IA brut de relecture → dict {flags:[...]}. Isolé pour être mockable."""
    import json
    import anthropic
    from . import services

    src = source if isinstance(source, str) else '[document image fourni séparément]'
    prompt = (CRITIQUE_PROMPT
              .replace('{source}', src[:20000])
              .replace('{content}', json.dumps(content, ensure_ascii=False)[:20000]))
    client = anthropic.Anthropic(api_key=services.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=services.CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}],
    )
    raw = response.content[0].text
    return services._loads_json_resilient(raw)


def ai_quality_check(content, source):
    """Drapeaux sémantiques (severity 'warn'). Fail-safe : toute erreur → []."""
    if not source:
        return []
    try:
        data = call_critique(content, source)
    except Exception as e:
        logger.warning('Critique IA indisponible : %s', e)
        return []
    flags = []
    for f in (data.get('flags') or []):
        if not isinstance(f, dict):
            continue
        flags.append(_flag(
            f.get('block') or 'concepts', f.get('concept_id'),
            f.get('item_id') or '?', 'warn', 'ai_doubt',
            f.get('reason') or 'À vérifier (relecture IA).',
        ))
    return flags


# ── 3. Orchestration ──────────────────────────────────────────────────────────

_SEVERITY_ORDER = {'error': 0, 'warn': 1}


def quality_check(content, source=None):
    """Union déterministe + critique IA, triée (error avant warn)."""
    flags = structural_check(content) + ai_quality_check(content, source)
    flags.sort(key=lambda f: _SEVERITY_ORDER.get(f['severity'], 9))
    return flags
