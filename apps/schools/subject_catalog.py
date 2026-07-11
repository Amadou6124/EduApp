"""
Catalogue de référence des matières du programme national malien.

But : une école neuve ne repart plus d'une liste vide. Pour chaque NIVEAU de classe
(les mêmes codes que `Level` dans models.py), on connaît les matières standard —
l'app les propose, le directeur applique en un clic, puis règle ses coefficients.

Principes (voir la maquette validée) :
- SUGGÉRÉ, jamais forcé : le directeur coche/décoche, le « + » manuel reste dispo.
- L'école POSSÈDE : appliquer = créer ses propres `Subject`, qu'elle édite librement.
- UNE couleur par MATIÈRE, pas par niveau : « Mathématiques » est vert partout
  (EDT, badges, bulletins) — cohérence visuelle dans toute l'app.

Ce module est de la DONNÉE PURE : il n'importe aucun modèle (évite tout import
circulaire ; models.py l'importe en lazy pour les couleurs/abréviations canoniques).
Les coefficients ne figurent PAS ici : ils restent réglés par chaque école.

Fiabilité (recherche sourcée, juillet 2026) :
- Fondamental 2ᵉ cycle & Secondaire général : matières confirmées par les annales DEF/BAC.
- Préscolaire & Fondamental 1ᵉ cycle : standard établi (pas de PDF officiel unique).
- Secondaire professionnel : socle général ; le technique dépend de la filière.
"""

from apps.core.text import norm_name

# ── Couleur canonique par matière ────────────────────────────────────────────
# Une seule teinte par matière, réutilisée à chaque niveau où elle apparaît.
# Couleurs distinctes (issues de la palette maison) pour éviter les collisions.
_COLORS = {
    'Français':                     '#7F77DD',
    'Mathématiques':                '#1D9E75',
    'Physique-Chimie':              '#D85A30',
    'SVT (Biologie)':               '#0F6E56',
    'Histoire-Géographie':          '#BA7517',
    'Éducation Civique et Morale':   '#7C3AED',
    'Anglais':                      '#378ADD',
    'Éducation Physique et Sportive':'#D4537E',
    'Philosophie':                  '#534AB7',
    'Arabe':                        '#0891B2',
    'Économie':                     '#B45309',
    'Comptabilité / Gestion':       '#993C1D',
    'Dessin / Arts plastiques':     '#DB2777',
    'Chant / Musique':              '#65A30D',
    "Sciences d'Observation":       '#0D9488',
    'Langue nationale':             '#6D28D9',
    '2ᵉ langue vivante':            '#185FA5',
    # Préscolaire — domaines d'éveil
    'Langage et Communication':      '#7F77DD',
    'Pré-mathématiques':            '#1D9E75',
    'Découverte du monde / Éveil':  '#0D9488',
    'Graphisme et Pré-écriture':     '#185FA5',
    'Activités sensorielles':       '#D4537E',
    'Éducation artistique':         '#DB2777',
    'Psychomotricité / EPS':        '#EA580C',
    'Vie en société et bonnes manières': '#BA7517',
    # Professionnel
    'Matières techniques de la filière': '#6D28D9',
}

# ── Abréviation canonique par matière ────────────────────────────────────────
_ABBREV = {
    'Français':                     'FRA',
    'Mathématiques':                'MATH',
    'Physique-Chimie':              'PC',
    'SVT (Biologie)':               'SVT',
    'Histoire-Géographie':          'HG',
    'Éducation Civique et Morale':   'ECM',
    'Anglais':                      'ANG',
    'Éducation Physique et Sportive':'EPS',
    'Philosophie':                  'PHILO',
    'Arabe':                        'AR',
    'Économie':                     'ECO',
    'Comptabilité / Gestion':       'COMPTA',
    'Dessin / Arts plastiques':     'ART',
    'Chant / Musique':              'MUS',
    "Sciences d'Observation":       'SO',
    'Langue nationale':             'LN',
    '2ᵉ langue vivante':            'LV2',
    'Langage et Communication':      'LANG',
    'Pré-mathématiques':            'PMATH',
    'Découverte du monde / Éveil':  'EVEIL',
    'Graphisme et Pré-écriture':     'GRAPH',
    'Activités sensorielles':       'SENS',
    'Éducation artistique':         'ART',
    'Psychomotricité / EPS':        'PSY',
    'Vie en société et bonnes manières': 'VIE',
    'Matières techniques de la filière': 'TECH',
}


def _m(name, optional=False):
    """Fabrique une entrée matière {nom, abréviation, couleur, optionnel}."""
    return {
        'name':     name,
        'abbrev':   _ABBREV.get(name, ''),
        'color':    _COLORS.get(name, ''),
        'optional': optional,
    }


# ── Catalogue par niveau (codes = Level.values de models.py) ──────────────────
CATALOG = {
    'prescolaire': [
        _m('Langage et Communication'),
        _m('Pré-mathématiques'),
        _m('Découverte du monde / Éveil'),
        _m('Graphisme et Pré-écriture'),
        _m('Activités sensorielles'),
        _m('Éducation artistique'),
        _m('Psychomotricité / EPS'),
        _m('Vie en société et bonnes manières'),
    ],
    'fondamental_1': [
        _m('Français'),
        _m('Mathématiques'),
        _m("Sciences d'Observation"),
        _m('Histoire-Géographie'),
        _m('Éducation Civique et Morale'),
        _m('Éducation Physique et Sportive'),
        _m('Dessin / Arts plastiques'),
        _m('Chant / Musique'),
        _m('Anglais',          optional=True),
        _m('Langue nationale', optional=True),
    ],
    'fondamental_2': [
        _m('Français'),
        _m('Mathématiques'),
        _m('Physique-Chimie'),
        _m('SVT (Biologie)'),
        _m('Histoire-Géographie'),
        _m('Éducation Civique et Morale'),
        _m('Anglais'),
        _m('Éducation Physique et Sportive'),
        _m('Arabe', optional=True),
    ],
    'secondaire_gen': [
        _m('Français'),
        _m('Philosophie'),
        _m('Mathématiques'),
        _m('Histoire-Géographie'),
        _m('Anglais'),
        _m('Éducation Physique et Sportive'),
        _m('2ᵉ langue vivante', optional=True),
    ],
    'secondaire_pro': [
        _m('Français'),
        _m('Mathématiques'),
        _m('Anglais'),
        _m('Comptabilité / Gestion'),
        _m('Éducation Physique et Sportive'),
        _m('Matières techniques de la filière', optional=True),
    ],
}

# ── Séries de Terminale (Secondaire général) ──────────────────────────────────
# Informatif : matières dominantes par série. Non appliqué automatiquement (le
# tronc commun l'est) — sert d'aide à la configuration fine du lycée.
SERIES = [
    {'code': 'TSE-STI', 'name': 'Sciences Exactes',       'subjects': ['Mathématiques', 'Physique-Chimie', 'SVT (Biologie)']},
    {'code': 'TSExp',   'name': 'Sciences Expérimentales','subjects': ['SVT (Biologie)', 'Physique-Chimie', 'Mathématiques']},
    {'code': 'TSEco',   'name': 'Sciences Économiques',   'subjects': ['Économie', 'Comptabilité / Gestion', 'Mathématiques', 'Histoire-Géographie']},
    {'code': 'TSS',     'name': 'Sciences Sociales',      'subjects': ['Philosophie', 'Histoire-Géographie']},
    {'code': 'TLL',     'name': 'Langues-Lettres',        'subjects': ['Français', '2ᵉ langue vivante', 'Philosophie']},
    {'code': 'TAL',     'name': 'Arts-Lettres',           'subjects': ['Arabe', 'Français', 'Philosophie']},
]


# ── API ───────────────────────────────────────────────────────────────────────
def suggested_subjects_for_level(level):
    """Liste des matières standard pour un niveau de classe (Level.value).

    Renvoie une liste de dicts {name, abbrev, color, optional}. Liste vide si le
    niveau est inconnu (jamais d'erreur — l'appelant affiche simplement « aucune
    suggestion »)."""
    return list(CATALOG.get(level, []))


def has_catalog(level):
    """Vrai si un catalogue existe pour ce niveau."""
    return bool(CATALOG.get(level))


# Index normalisé nom → entrée, pour les recherches canoniques (insensible casse/accents).
_BY_NORM = {norm_name(m['name']): m for subs in CATALOG.values() for m in subs}


def canonical_color(name):
    """Couleur canonique d'une matière d'après son nom (normalisé), sinon ''."""
    m = _BY_NORM.get(norm_name(name))
    return m['color'] if m else ''


def canonical_abbrev(name):
    """Abréviation canonique d'une matière d'après son nom (normalisé), sinon ''."""
    m = _BY_NORM.get(norm_name(name))
    return m['abbrev'] if m else ''
