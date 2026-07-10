"""Le Cahier (Chantier « le cahier d'abord ») — dérivation SANS IA (Voie B).

Philosophie : l'app ne remplace pas le cahier, elle le commande. Elle prescrit
un travail À LA MAIN, lit à voix haute / révèle le modèle, et l'élève s'AUTO-
corrige. L'app ne lit JAMAIS l'écriture.

Voie B : aucun appel IA — on dérive du contenu DÉJÀ généré (lecture B2 + concepts
B1). Marche sur toutes les leçons existantes, zéro coût, zéro régénération.

Matrice NIVEAU × MATIÈRE (validée) — la forme vient du niveau, le contenu de la matière :
  • 📝 Copie          → socle universel (toutes matières, tous niveaux) ; COMPLÉMENT seul
  • 🎧 Dictée flash   → SEULEMENT langue/littéraire, SEULEMENT préscolaire→fondamental 2
       préparée         (jamais lycée, jamais maths). = préparation des mots + SÉRIE de phrases
  • ✍️ Composition    → fondamental 2 et +, PLUSIEURS, forme selon la matière

Le nœud Cahier n'apparaît que s'il y a une VRAIE tâche d'écriture (dictée OU
composition). La copie seule ne suffit pas (« ça ne colle pas » pour les petits
en maths → pas de nœud).

Robustesse : le subject_type réel est incohérent ('lang' vs 'language', 'other'
pour des maths) → on croise TOUJOURS subject_type ET le nom de la matière.
"""
import re
import unicodedata

# Niveaux « bas » : phrases courtes, version « simple » de la lecture.
_LOW_LEVELS = {'prescolaire', 'fondamental_1'}
# Dictée : seulement ces niveaux (jamais secondaire/supérieur).
_DICTEE_LEVELS = {'prescolaire', 'fondamental_1', 'fondamental_2'}
# Composition : fondamental 2 et au-dessus.
_COMPO_LEVELS = {'fondamental_2', 'secondaire_gen', 'secondaire_pro', 'superieur'}

# subject_type indiquant une matière de langue (tolère la donnée réelle 'lang').
_LANG_TYPES = {'language', 'lang', 'literary'}
# Indices dans le NOM de la matière (secours quand subject_type est faux).
# Sans accents (le nom est normalisé avant comparaison) → « francais » couvre « Français ».
_LANG_NAME_HINTS = ('franc', 'anglais', 'arabe', 'allemand', 'espagnol', 'langue',
                    'lecture', 'litter', 'orthograph', 'grammaire',
                    'expression', 'communication')

MAX_DICTEE = 3      # phrases de la série (flash)
MAX_COMPO = 3       # compositions (une par concept)
MAX_PREP = 5        # mots à préparer


# ── Découpe / mots ────────────────────────────────────────────────────────────

def _sentences(text):
    parts = re.split(r'(?<=[.!?…])\s+', (text or '').strip())
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def _hot_words(sentence, n=2):
    """1-2 mots « pièges » (les plus longs). Aide visuelle, jamais bloquant."""
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]{6,}", sentence or '')
    out = []
    for w in sorted(words, key=len, reverse=True):
        if w.lower() not in [u.lower() for u in out]:
            out.append(w)
        if len(out) >= n:
            break
    return out


# ── Détection robuste du type de matière ──────────────────────────────────────

def _strip_accents(s):
    """« Français » → « francais », « géo » → « geo » (comparaison robuste aux accents)."""
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def _norm(lesson):
    st = (getattr(lesson, 'subject_type', '') or '').lower()
    name = _strip_accents((getattr(lesson, 'subject', '') or '').lower())
    return st, name


def _is_language(lesson):
    """Matière de langue ? subject_type OU nom (robuste à la donnée incohérente)."""
    st, name = _norm(lesson)
    if st in _LANG_TYPES:
        return True
    return any(h in name for h in _LANG_NAME_HINTS)


_COMPO_FORMS = {
    'math':       "Résous cet exercice et rédige toute ta démarche : {c}.",
    'scientific': "Explique et décris sur ta feuille : {c}.",
    'geography':  "Rédige un paragraphe organisé : {c}.",
    'accounting': "Pose et résous l'écriture comptable : {c}.",
    'code':       "Écris l'algorithme à la main : {c}.",
    'letters':    "Rédige un court texte bien construit : {c}.",
    'generic':    "Rédige sur ta feuille ce que tu as retenu : {c}.",
}


def _compo_form(lesson):
    """Modèle de consigne de composition, selon la matière (subject_type + nom)."""
    st, name = _norm(lesson)

    def has(*keys):
        return any(k in name for k in keys)

    if st == 'math' or has('math'):
        return _COMPO_FORMS['math']
    if st == 'scientific' or has('scien', 'svt', 'physique', 'chimie', 'biolog'):
        return _COMPO_FORMS['scientific']
    if st == 'geography' or has('histoire', 'geo'):   # nom sans accents
        return _COMPO_FORMS['geography']
    if st == 'accounting' or has('comptab'):
        return _COMPO_FORMS['accounting']
    if st == 'code' or has('informat', 'algorith', 'program'):
        return _COMPO_FORMS['code']
    if st in ('language', 'lang', 'literary') or _is_language(lesson) or has('philo'):
        return _COMPO_FORMS['letters']
    return _COMPO_FORMS['generic']


# ── Dictée : série de phrases + préparation ───────────────────────────────────

def _dictee_candidates(reading, low):
    sents = []
    for sec in (reading.get('sections') or []):
        if not isinstance(sec, dict):
            continue
        for b in (sec.get('blocks') or []):
            if not isinstance(b, dict):
                continue
            src = ((b.get('simple') if low else '') or b.get('text') or '')
            sents.extend(_sentences(src))
    return sents


def _pick_dictee_series(reading, low, maxn=MAX_DICTEE):
    """Série de phrases (flash) dans la fenêtre de longueur du niveau. Déterministe."""
    sents = _dictee_candidates(reading, low)
    if not sents:
        return []
    lo, hi = (18, 75) if low else (40, 150)
    window = [s for s in sents if lo <= len(s) <= hi] or sents
    seen, out = set(), []
    for s in window:
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= maxn:
            break
    return out


def _prep_words(sentences, reading):
    """Mots à étudier AVANT la dictée (levier n°1) : les mots pièges des phrases,
    avec leur définition si le glossaire la contient. [{word, hint}]."""
    terms = reading.get('terms') if isinstance(reading.get('terms'), dict) else {}
    terms_low = {k.lower(): v for k, v in terms.items()
                 if isinstance(k, str) and isinstance(v, str)}
    out, seen = [], set()
    for s in sentences:
        for w in _hot_words(s, n=2):
            wl = w.lower()
            if wl in seen:
                continue
            seen.add(wl)
            out.append({'word': w, 'hint': terms_low.get(wl, '')})
            if len(out) >= MAX_PREP:
                return out
    return out


def _concept_model(concept):
    """Repère d'auto-correction d'une composition : explications déjà rédigées."""
    bits = []
    for q in (concept.get('quiz') or []):
        exp = (q.get('explanation') or '').strip()
        if exp and exp not in bits:
            bits.append(exp)
    return ' '.join(bits[:3])


# ── Dérivation ────────────────────────────────────────────────────────────────

def derive_cahier_tasks(cv, lesson):
    """Dérive les tâches Cahier d'une version de contenu (liste de dicts), vide si
    le contenu ne s'y prête pas (→ pas de nœud). Entièrement défensif.

    Task kinds :
      'prep'       { words: [{word, hint}] }       — préparation (avant dictée)
      'dictee'     { text, hot }                    — une phrase de la série (flash)
      'production' { prompt, text, hot }            — une composition (forme par matière)
      'copie'      { text, hot }                    — recopier une définition (complément)
    text = le MODÈLE révélé à la correction.
    """
    reading = cv.reading_data if isinstance(cv.reading_data, dict) else {}
    concepts = cv.concepts_data if isinstance(cv.concepts_data, list) else []
    level = getattr(lesson, 'level', '') or ''
    low = level in _LOW_LEVELS

    tasks = []

    # 1. Dictée flash PRÉPARÉE — langue/littéraire + préscolaire→fondamental 2
    dictee_sentences = []
    if _is_language(lesson) and level in _DICTEE_LEVELS:
        dictee_sentences = _pick_dictee_series(reading, low)
        if dictee_sentences:
            prep = _prep_words(dictee_sentences, reading)
            if prep:
                tasks.append({
                    'id': 'prep', 'kind': 'prep', 'label': 'Préparation',
                    'prompt': "Regarde bien ces mots avant d'écrire.",
                    'words': prep, 'text': '', 'hot': [],
                })
            for i, s in enumerate(dictee_sentences):
                tasks.append({
                    'id': f'dictee{i + 1}', 'kind': 'dictee', 'label': 'Dictée',
                    'prompt': 'Écoute la phrase, puis écris-la sur ton cahier.',
                    'text': s, 'hot': _hot_words(s),
                })

    # 2. Compositions — fondamental 2 et +, PLUSIEURS, forme selon la matière.
    #    Si la dictée est déjà présente (fond. 2 langue), on n'en met qu'UNE (la
    #    dictée est le cœur à ce niveau) → on ne noie pas l'élève.
    compo_cap = 1 if dictee_sentences else MAX_COMPO
    if level in _COMPO_LEVELS and concepts:
        form = _compo_form(lesson)
        added = 0
        for c in concepts:
            if added >= compo_cap:
                break
            if not isinstance(c, dict):
                continue
            name = (c.get('name') or '').strip()
            if not name:
                continue
            tasks.append({
                'id': f'prod{added + 1}', 'kind': 'production', 'label': 'Composition',
                'prompt': form.format(c=name), 'text': _concept_model(c) or name, 'hot': [],
            })
            added += 1

    # Le nœud n'existe que s'il y a une VRAIE tâche d'écriture (dictée ou compo).
    if not any(t['kind'] in ('dictee', 'production') for t in tasks):
        return []

    # 3. Copie — complément universel (une définition), en fin de série.
    terms = reading.get('terms') if isinstance(reading.get('terms'), dict) else {}
    term = next(((k, v) for k, v in terms.items()
                 if isinstance(k, str) and isinstance(v, str) and k and v), None)
    if term:
        word, definition = term
        tasks.append({
            'id': 'copie', 'kind': 'copie', 'label': 'Copie',
            'prompt': 'Recopie proprement cette définition sur ton cahier.',
            'text': f'{word} : {definition}', 'hot': [word],
        })

    return tasks


def has_cahier(cv, lesson):
    """Le nœud Cahier doit-il apparaître ? (dérivation légère)."""
    return bool(derive_cahier_tasks(cv, lesson))
