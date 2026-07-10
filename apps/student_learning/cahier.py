"""Le Cahier (Chantier « le cahier d'abord ») — dérivation SANS IA.

Philosophie : l'app ne remplace pas le cahier, elle le commande. Elle prescrit
un travail À LA MAIN (dictée, copie, composition), lit à voix haute / révèle le
modèle, et l'élève s'AUTO-corrige. L'app ne lit jamais l'écriture.

Voie B (décidée) : on ne fait AUCUN appel IA — on dérive les tâches du contenu
DÉJÀ généré (lecture B2 + concepts B1). Donc ça marche sur toutes les leçons
existantes, sans coût ni régénération. Un bloc IA dédié = niveau 2 plus tard.

Calibrage par niveau (Lesson.level) :
  • bas  (préscolaire, fondamental 1) : dictée COURTE (texte « simple ») + copie
  • haut (secondaire, supérieur)      : + une composition « prends ta feuille »
La FORME vient du niveau, le CONTENU de la matière — les deux sont déjà connus.
"""
import re

# Niveaux « bas » : phrases courtes, version simplifiée de la lecture.
_LOW_LEVELS = {'prescolaire', 'fondamental_1'}
# Niveaux « hauts » : on ajoute une composition (production à la main).
_HIGH_LEVELS = {'secondaire_gen', 'secondaire_pro', 'superieur'}

MAX_TASKS = 3


def _sentences(text):
    """Découpe un texte en phrases exploitables (assez longues, propres)."""
    parts = re.split(r'(?<=[.!?…])\s+', (text or '').strip())
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def _hot_words(sentence, n=2):
    """Repère 1-2 mots « pièges » à souligner à la correction : les plus longs,
    hors ponctuation. Purement indicatif (aide visuelle), jamais bloquant."""
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]{6,}", sentence or '')
    uniq = []
    for w in sorted(words, key=len, reverse=True):
        wl = w.lower()
        if wl not in [u.lower() for u in uniq]:
            uniq.append(w)
        if len(uniq) >= n:
            break
    return uniq


def _pick_dictee(reading, low):
    """Choisit UNE phrase de dictée dans la lecture. Bas niveau → version
    « simple » et phrase courte ; sinon texte normal, phrase moyenne.
    Déterministe (1re phrase de la fenêtre de longueur) → stable entre les rendus."""
    sents = []
    for sec in (reading.get('sections') or []):
        if not isinstance(sec, dict):
            continue
        for b in (sec.get('blocks') or []):
            if not isinstance(b, dict):
                continue
            src = ((b.get('simple') if low else '') or b.get('text') or '')
            sents.extend(_sentences(src))
    if not sents:
        return None
    if low:
        window = [s for s in sents if 18 <= len(s) <= 75]
    else:
        window = [s for s in sents if 40 <= len(s) <= 150]
    return (window or sents)[0]


def _concept_model(concept):
    """Modèle indicatif d'une composition : le nom du concept + les explications
    de ses quiz (déjà rédigées par l'IA). Sert de repère d'auto-correction, pas
    d'un corrigé de dissertation (enrichi en niveau 2)."""
    bits = []
    for q in (concept.get('quiz') or []):
        exp = (q.get('explanation') or '').strip()
        if exp and exp not in bits:
            bits.append(exp)
    return ' '.join(bits[:3])


def derive_cahier_tasks(cv, lesson):
    """Dérive les tâches Cahier d'une version de contenu. Retourne une liste de
    dicts (au plus MAX_TASKS), vide si le contenu ne s'y prête pas (→ pas de nœud).

    Task = { id, kind ('dictee'|'copie'|'production'), label, prompt, text, hot[] }
      text = le MODÈLE révélé à la correction (phrase de dictée / règle / repère).
    Entièrement défensif : toute donnée absente ou malformée → tâche sautée."""
    reading = cv.reading_data if isinstance(cv.reading_data, dict) else {}
    concepts = cv.concepts_data if isinstance(cv.concepts_data, list) else []
    level = getattr(lesson, 'level', '') or ''
    low = level in _LOW_LEVELS
    high = level in _HIGH_LEVELS

    tasks = []

    # 1. Dictée — depuis la lecture (le cœur, tous niveaux)
    sent = _pick_dictee(reading, low)
    if sent:
        tasks.append({
            'id': 'dictee', 'kind': 'dictee', 'label': 'Dictée',
            'prompt': 'Écoute la phrase, puis écris-la sur ton cahier.',
            'text': sent, 'hot': _hot_words(sent),
        })

    # 2. Copie — une définition du glossaire (mémoire de l'orthographe / du sens)
    terms = reading.get('terms') if isinstance(reading.get('terms'), dict) else {}
    term = next((( k, v) for k, v in terms.items()
                 if isinstance(k, str) and isinstance(v, str) and k and v), None)
    if term:
        word, definition = term
        tasks.append({
            'id': 'copie', 'kind': 'copie', 'label': 'Copie',
            'prompt': 'Recopie proprement cette définition sur ton cahier.',
            'text': f'{word} : {definition}', 'hot': [word],
        })

    # 3. Composition — seulement aux niveaux hauts (produire à la main = clé du BAC)
    if high and concepts:
        c = concepts[0] if isinstance(concepts[0], dict) else {}
        name = (c.get('name') or '').strip()
        model = _concept_model(c)
        if name:
            tasks.append({
                'id': 'production', 'kind': 'production', 'label': 'Composition',
                'prompt': f'Compose sur ta feuille : {name}.',
                'text': model or name, 'hot': [],
            })

    return tasks[:MAX_TASKS]


def has_cahier(cv, lesson):
    """Le nœud Cahier doit-il apparaître pour cette leçon ? (dérivation légère)."""
    return bool(derive_cahier_tasks(cv, lesson))
