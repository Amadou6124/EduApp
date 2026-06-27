"""
Services Phase 2 — génération de leçons par IA.

Flux : fichier source (PDF/image/texte) → extraction → appel Claude (single-pass
texte OU images) → JSON structuré → mapping des 4 JSONField de Lesson.

NB : le prompt contient énormément d'accolades JSON littérales, donc on assemble
les variables avec str.replace() (PAS str.format(), qui interprète chaque { } comme
un champ de format et planterait).
"""
import base64
import io
import json
import logging
import random
import re
import threading
import time
import unicodedata
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import anthropic
import pdfplumber
import pypdfium2 as pdfium
from decouple import config

from django.db import transaction, close_old_connections
from django.db.models import Q
from django.utils import timezone

from .models import (Lesson, LessonStatus, AIProvider, SubjectType,
                     EducationLevel, Unit, LessonContentVersion)

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
CLAUDE_MODEL      = 'claude-sonnet-4-6'
CLAUDE_MAX_TOKENS = 16_000

# Coût par million de tokens (USD) — ajuster si la grille tarifaire change.
CLAUDE_INPUT_COST_PER_M  = Decimal('3.00')
CLAUDE_OUTPUT_COST_PER_M = Decimal('15.00')

# Marqueur de la section "contenu" du prompt — réutilisé pour le mode images.

EXTRACTION_PROMPT = """Tu es un transcripteur. On te donne la PHOTO d'une page de cahier ou d'un manuel scolaire.

Transcris FIDÈLEMENT tout le texte pédagogique visible, sans rien résumer ni interpréter.
- Conserve la structure : titres, sous-titres, listes, numérotation, formules.
- Restitue les formules mathématiques en notation lisible (ex: (a+b)^2, 3/4, x²).
- Ignore les gribouillis, ratures, numéros de page, marges décoratives.
- Si un passage est illisible, écris [illisible] à sa place — n'invente jamais.
- Réponds UNIQUEMENT avec le texte transcrit, sans commentaire de ta part."""


# ─── 1. Extraction de contenu ────────────────────────────────────────────────

def extract_content_from_file(file_path: str, source_type: str):
    """
    Extrait le contenu d'un fichier source.
    Retourne soit :
    - str : texte extrait (PDF texte natif / fichier texte)
    - list[dict] : images base64 [{'type','data','media_type'}] (PDF scanné ou photo)
    """
    path = Path(file_path)

    if source_type == 'text':
        return path.read_text(encoding='utf-8')

    if source_type == 'pdf':
        text = _extract_pdf_text(path)
        if text and len(text.strip()) > 100:
            logger.info('PDF texte extrait: %d chars', len(text))
            return text
        logger.info('PDF scanné détecté -> rendu en images')
        return _render_pdf_as_images(path)

    if source_type == 'image':
        return _image_to_base64_block(path)

    raise ValueError(f'source_type inconnu: {source_type}')


def _extract_pdf_text(path: Path) -> str:
    """Extraction texte natif via pdfplumber."""
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return '\n\n'.join(pages)
    except Exception as e:
        logger.warning('pdfplumber failed: %s', e)
        return ''


def _render_pdf_as_images(path: Path) -> list:
    """Rend chaque page PDF en image base64 JPEG (PDF scannés)."""
    images = []
    try:
        pdf = pdfium.PdfDocument(str(path))
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            bitmap = page.render(scale=2)
            pil_image = bitmap.to_pil()

            buffer = io.BytesIO()
            pil_image.save(buffer, format='JPEG', quality=85)
            b64 = base64.standard_b64encode(buffer.getvalue()).decode('utf-8')

            images.append({'type': 'image', 'data': b64, 'media_type': 'image/jpeg'})
        pdf.close()
    except Exception as e:
        logger.error('pypdfium2 render failed: %s', e)
        raise

    return images


def _image_to_base64_block(path: Path) -> list:
    """Convertit une image en bloc base64."""
    suffix = path.suffix.lower()
    media_type = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    }.get(suffix, 'image/jpeg')
    b64 = base64.standard_b64encode(path.read_bytes()).decode('utf-8')
    return [{'type': 'image', 'data': b64, 'media_type': media_type}]


# ─── 2. Construction du prompt ───────────────────────────────────────────────



# ─── Validation du fichier uploadé ───────────────────────────────────────────

MAGIC_BYTES = {
    b'%PDF': 'pdf',
    b'\xff\xd8\xff': 'image',
    b'\x89PNG': 'image',
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_lesson_file(file) -> str:
    """
    Valide type (magic bytes) + taille du fichier uploadé.
    Retourne le source_type ('pdf' ou 'image'). Lève ValueError si invalide.
    """
    if file.size > MAX_FILE_SIZE:
        raise ValueError(
            f'Fichier trop volumineux ({file.size // 1024}KB). Maximum : 10MB.'
        )

    header = file.read(4)
    file.seek(0)

    for magic, ftype in MAGIC_BYTES.items():
        if header.startswith(magic):
            return ftype

    raise ValueError(
        'Type de fichier non autorisé. Seuls les PDF et images (JPG, PNG) sont acceptés.'
    )


# ─── Phase 6 — Évaluation des quiz ───────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalise pour comparaison souple : minuscules, sans accents, espaces réduits."""
    text = (text or '').strip().lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return ' '.join(text.split())


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Temps 1 : Prompt Architecte (A.1)
# ───────────────────────────────────────────────────────────────────────────────
# Construit EN PARALLÈLE de l'existant : ne modifie ni SYSTEM_PROMPT, ni
# generate_lesson_with_ai, ni _call_claude, ni _parse_and_validate, ni
# evaluate_answer. Document → structure { unit_title, subject, direction,
# lessons[] } (cf. PORTAL_V2_SPEC §4.2). Le contenu détaillé (Temps 2) viendra
# ensuite, leçon par leçon.
# ═══════════════════════════════════════════════════════════════════════════════

# Sortie légère (structure unité + leçons) → plafond bas, pas les 16k de la génération.
ARCHITECT_MAX_TOKENS = 4_000

ARCHITECT_PROMPT = """Tu es un concepteur pédagogique malien expert. Tu connais le système éducatif
du Mali — du préscolaire à l'enseignement supérieur — et ses matières : français,
maths, sciences (SVT, physique-chimie), histoire-géographie, anglais, philosophie,
informatique, droit, comptabilité, ainsi que l'éducation islamique et le fiqh en
arabe.

TA MISSION
Tu reçois UN document de cours fourni par un enseignant. Ce document peut être :
- du texte,
- OU un document visuel (PDF scanné, page photographiée au téléphone) que tu lis
  directement avec ta vision.
Tu dois proposer un DÉCOUPAGE de ce document en une UNITÉ et une liste de LEÇONS.

TU NE GÉNÈRES AUCUN CONTENU.
Pas de quiz, pas d'histoire, pas de texte de lecture, pas d'examen. UNIQUEMENT la
structure : le titre de l'unité et la liste des leçons (titre + résumé d'une phrase).
Le contenu détaillé sera généré dans une étape ultérieure, leçon par leçon.

PRINCIPE DE DÉCOUPAGE (le cœur de ta tâche)
- Une LEÇON est une unité d'apprentissage DIGESTE : un sous-thème cohérent qu'un
  élève peut assimiler d'un seul tenant. Ce n'est PAS un découpage mécanique par
  pages ou par paragraphes.
- Raisonne sur le SENS : regroupe ce qui va ensemble, sépare les thèmes distincts.
- Référence indicative (souple, pas une règle) : une leçon tient en environ une
  séance de cours.
- Petit document portant sur UN seul thème = UNE SEULE leçon. Ne découpe jamais
  artificiellement un contenu qui forme un tout.
- Gros document = plusieurs leçons logiques. Exemple : un document de 60 pages sur
  « La Chine » se découpe en leçons comme « Le relief », « Le climat »,
  « La population », « L'économie », etc.
- Si le document couvre plusieurs sujets SANS lien clair entre eux, regroupe-les
  sous l'unité la plus représentative et signale-le dans les résumés des leçons
  concernées. Une SEULE unité par appel (tu ne produis jamais plusieurs unités).

DÉTECTION AUTOMATIQUE
- subject : déduis la matière ET le niveau à partir du document
  (ex. « Histoire-Géographie — Terminale »).
- direction : « rtl » si le document est rédigé en arabe (fiqh, éducation
  islamique), sinon « ltr ».
- unit_title : un titre d'unité clair et fidèle au document.

GARDE-FOU LECTURE
Si le document est ILLISIBLE — page vide, scan trop flou ou trop sombre, écriture
manuscrite indéchiffrable, contenu incohérent — n'INVENTE PAS de structure.
Retourne à la place l'objet d'erreur prévu ci-dessous.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
Tu réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant, aucun texte
après, aucun bloc markdown. Le premier caractère est { et le dernier est }.

Cas normal — découpage réussi :
{
  "unit_title": "La Chine",
  "subject": "Histoire-Géographie — Terminale",
  "direction": "ltr",
  "lessons": [
    { "id": "le-relief", "title": "Le relief de la Chine",
      "summary": "Les grands ensembles de relief : montagnes de l'ouest, plaines de l'est." },
    { "id": "le-climat", "title": "Le climat",
      "summary": "Les zones climatiques et la mousson, du nord aride au sud humide." },
    { "id": "la-population", "title": "La population",
      "summary": "Répartition, densités et grandes villes de la Chine." }
  ]
}

Cas document illisible :
{
  "error": "unreadable",
  "message": "Document difficile à lire (qualité ou écriture manuscrite). Réessaie avec un document plus net, un fichier texte, ou colle le contenu directement."
}

CONTRAINTES
- JSON valide uniquement.
- "id" = slug stable : minuscules, mots séparés par des tirets, sans accents ni
  espaces (ex. « la-population »).
- "summary" = une phrase courte et informative : elle aide l'enseignant à VALIDER
  le découpage, donc elle doit dire clairement ce que couvre la leçon.
- Respecte la langue du document pour les titres et résumés.

RAPPEL IMPORTANT SUR LE NOMBRE DE LEÇONS
Le nombre de leçons doit refléter le CONTENU RÉEL, jamais un minimum à atteindre.
S'il n'y a qu'un seul thème, renvoie UNE SEULE leçon dans le tableau "lessons".
Ne multiplie jamais les leçons par mimétisme de l'exemple ci-dessus : un document
court et mono-thème = une seule leçon, et c'est parfaitement correct.

DOCUMENT À STRUCTURER :
{content}"""


def _loads_json_resilient(raw: str) -> dict:
    """json.loads avec récupération : direct → json-repair → troncature après dernière }.

    Même stratégie que _parse_and_validate, isolée pour réemploi par le pipeline v2
    (on ne modifie pas _parse_and_validate — duplication assumée et voulue)."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        try:
            from json_repair import repair_json
            return json.loads(repair_json(raw))
        except Exception:
            try:
                last = raw.rfind('}')
                return json.loads(raw[:last + 1])
            except Exception:
                raise ValueError(f'JSON invalide: {e}\nDébut de la réponse: {raw[:200]}')


def call_architect(content, cost_sink: list = None) -> dict:
    """Temps 1 (A.1) : document → structure { unit_title, subject, direction, lessons[] }.

    `content` = str (texte extrait) OU list de blocs image base64 (sortie de
    extract_content_from_file), exactement comme l'attend _call_claude.

    Retourne :
      - un dict structure valide { unit_title, subject, direction, lessons[] }, OU
      - { 'error': 'unreadable', 'message': ... } si Claude juge le document illisible.
    Lève ValueError si la réponse JSON est inexploitable.
    NE TOUCHE PAS au pipeline existant (generate_lesson_with_ai)."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if isinstance(content, str):
        # Entrée texte : le contenu est injecté dans le prompt.
        user_content = [{'type': 'text', 'text': ARCHITECT_PROMPT.replace('{content}', content)}]
    else:
        # Entrée visuelle (PDF scanné / photo) : vision native de Claude.
        user_content = [
            {'type': 'image',
             'source': {'type': 'base64', 'media_type': img['media_type'], 'data': img['data']}}
            for img in content
        ]
        prompt_imgs = ARCHITECT_PROMPT.replace('{content}', 'lis les images fournies ci-dessus.')
        user_content.append({'type': 'text', 'text': prompt_imgs})

    start = time.time()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=ARCHITECT_MAX_TOKENS,
        messages=[{'role': 'user', 'content': user_content}],
    )
    cost = (
        Decimal(response.usage.input_tokens) / 1_000_000 * CLAUDE_INPUT_COST_PER_M
        + Decimal(response.usage.output_tokens) / 1_000_000 * CLAUDE_OUTPUT_COST_PER_M
    )
    logger.info(
        'Architecte: %d in / %d out / $%.6f / %.1fs',
        response.usage.input_tokens, response.usage.output_tokens, cost, time.time() - start,
    )

    if cost_sink is not None:
        cost_sink.append(cost)

    return _parse_architect(response.content[0].text)


def _parse_architect(raw: str) -> dict:
    """Parse la sortie de l'Architecte. Distingue le cas 'unreadable' du cas normal."""
    data = _loads_json_resilient(raw)

    # Cas garde-fou lecture : remonté tel quel pour que l'appelant le détecte.
    if isinstance(data, dict) and data.get('error') == 'unreadable':
        return {'error': 'unreadable',
                'message': data.get('message', 'Document difficile à lire.')}

    # Cas normal : valider la forme attendue.
    required = ['unit_title', 'subject', 'direction', 'lessons']
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Structure Architecte incomplète, clés manquantes: {missing}")
    if not isinstance(data['lessons'], list) or not data['lessons']:
        raise ValueError("Architecte: 'lessons' vide ou invalide")
    if data.get('direction') not in ('ltr', 'rtl'):
        data['direction'] = 'ltr'  # défensif
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Temps 2 / Appel B1 : Prompt « Noyau pédagogique » (A.2)
# ───────────────────────────────────────────────────────────────────────────────
# Additif, en parallèle de l'existant et du code A.1. Une leçon (titre + résumé +
# portion source) → { color, guide, concepts[], exam }. NOYAU_PROMPT = corps de
# PORTAL_V2_SPEC §4.7 avec le marqueur [[CATALOGUE…]] remplacé par le catalogue
# des 13 types de §4.8. Approche réflexion-puis-JSON : on n'extrait que <json>.
# ═══════════════════════════════════════════════════════════════════════════════

# B1 est l'appel le PLUS lourd : <reflexion> (planification libre) + JSON =
# 3-6 concepts × 4-8 quiz + ~10-15 questions d'examen. 20k évite toute troncature ;
# on n'est facturé que sur la sortie réelle, donc surcoût négligeable.
NOYAU_MAX_TOKENS = 20_000

NOYAU_PROMPT = """Tu es un concepteur pédagogique malien expert, spécialiste de l'ÉVALUATION. Tu
connais le programme scolaire malien — du préscolaire au supérieur — ses matières
(français, maths, SVT, physique-chimie, histoire-géographie, anglais, philosophie,
informatique, droit, comptabilité, éducation islamique et fiqh en arabe) et tu
ancres tes exemples dans le quotidien malien (marché de Bamako, francs CFA, mangues,
transport, famille, champs, boutique, mosquée).

TA MISSION
Tu reçois la source d'UNE seule leçon (son titre, son résumé, et la portion de
document correspondante). Tu génères le NOYAU PÉDAGOGIQUE de cette leçon :
- les CONCEPTS,
- leurs QUIZ (selon les types autorisés ci-dessous),
- le découpage en PASSES,
- et l'EXAMEN.

Tu ne génères PAS le texte de lecture (« reading ») ni l'histoire (« story ») :
ils sont produits par d'autres appels. Concentre-toi uniquement sur le noyau.

APPROCHE EN 2 PHASES (obligatoire)
Tu réponds en deux blocs successifs et rien d'autre :

<reflexion>
Ici tu ANALYSES et PLANIFIES avant de produire le moindre JSON :
- identifie les concepts clés de la leçon (vise 3 à 6, selon la richesse réelle) ;
- repère les concepts RICHES qui méritent d'être découpés en plusieurs passes ;
- pour chaque concept, choisis les types de quiz qui le testent le mieux ;
- planifie ce que l'examen doit couvrir.
Ce bloc est un BROUILLON DE PLANIFICATION : écris-le librement, il sera IGNORÉ par
le serveur. Il sert uniquement à améliorer la qualité de ton JSON.
</reflexion>

<json>
Ici, et SEULEMENT ici, tu produis le JSON strict qui découle de ta réflexion.
Le serveur n'extrait QUE ce bloc.
</json>

PRINCIPES DE GÉNÉRATION DES CONCEPTS
- VOLUME ADAPTATIF : le nombre de concepts reflète la richesse RÉELLE du contenu.
  3 à 6 est une fourchette indicative, pas un quota : ne remplis jamais pour
  atteindre un minimum, ne tronque jamais une notion pour rester sous un maximum.
- Chaque concept = UNE idée maîtrisable, avec :
    "id"    : slug snake_case stable (ex. "transport_membranaire"),
    "name"  : nom lisible (ex. « Le transport membranaire »),
    "order" : position 1..N dans la leçon.
- 4 à 8 quiz par concept (indicatif, selon la richesse du concept).

DÉCOUPAGE EN PASSES
- Un concept avec PEU de quiz (moins de 8) → "passes": 1 (aucun découpage).
- Un concept RICHE → "passes": 2 à 4, par DIFFICULTÉ CROISSANTE ou par SOUS-THÈME.
- Chaque quiz porte un "pass_index" (0 = première passe, 1 = deuxième, etc.).
- Contraintes : 1 ≤ passes ≤ 4 ; tout pass_index est dans [0, passes-1] ; aucune
  passe ne doit être vide.

CHOIX DES TYPES DE QUIZ
- Choisis le type selon ce qui teste le MIEUX le concept — jamais pour « faire joli ».
- Privilégie une variété NATURELLE : tester un concept de plusieurs façons l'ancre
  mieux. Mais ne force pas la variété au détriment de la pertinence.
- N'utilise QUE les types décrits dans le catalogue ci-dessous.

LES 13 TYPES DE QUIZ AUTORISÉS

Voici les 13 SEULS types de quiz que tu peux générer. Pour chacun : son token
exact (champ "type"), les champs à produire, quand l'utiliser et le piège à
éviter. N'invente aucun autre type.

Champs communs à CHAQUE quiz : "id" (identifiant court), "type" (un des 13 tokens),
"instruction" (l'énoncé affiché à l'élève), le payload propre au type, et un
"explanation" optionnel (texte affiché après la réponse — recommandé quand
l'erreur est instructive).

POINT DE VIGILANCE — pass_index vs concept_id :
- un quiz placé DANS un concept ("concepts[].quiz[]") porte "pass_index" (le
  numéro de sa passe, 0-based) ;
- une question d'EXAMEN ("exam.questions[]") porte "concept_id" (la notion testée)
  et JAMAIS de "pass_index".

────────────────────────────────────────────────────────────────────────────
1. mcq_single — QCM à réponse unique
- Quand l'utiliser : une question avec UNE seule bonne réponse (toutes matières).
- Champs : "options" (liste de textes), "answer_index" (index de la bonne option).
- Exemple :
  { "type": "mcq_single", "instruction": "Quelle est la capitale du Mali ?",
    "options": ["Bamako", "Ouagadougou", "Dakar", "Niamey"], "answer_index": 0,
    "explanation": "Bamako est la capitale du Mali depuis 1908." }
- Piège : s'il y a plusieurs bonnes réponses, utilise mcq_multiple. "answer_index"
  doit bien pointer la bonne option.

────────────────────────────────────────────────────────────────────────────
2. mcq_multiple — QCM à réponses multiples
- Quand l'utiliser : plusieurs bonnes réponses à cocher (au moins 2).
- Champs : "options" (liste), "answer_indices" (liste des index corrects).
- Exemple :
  { "type": "mcq_multiple", "instruction": "Lesquelles de ces villes sont au Mali ?",
    "options": ["Ségou", "Abidjan", "Sikasso", "Mopti"], "answer_indices": [0, 2, 3],
    "explanation": "Abidjan est en Côte d'Ivoire." }
- Piège : prévois AU MOINS 2 bonnes réponses (sinon mcq_single). L'élève est jugé
  sur l'ensemble EXACT (ni oubli ni excès).

────────────────────────────────────────────────────────────────────────────
3. true_false — Vrai / Faux
- Quand l'utiliser : une affirmation franchement vraie ou fausse.
- Champs : "answer" (booléen true ou false).
- Exemple :
  { "type": "true_false", "instruction": "Le fleuve Niger traverse le Mali.",
    "answer": true, "explanation": "Le Niger traverse le Mali sur près de 1 700 km." }
- Piège : l'affirmation doit être NETTE, jamais ambiguë ou « ça dépend ».

────────────────────────────────────────────────────────────────────────────
4. k_prime — Grille Vrai/Faux (type K')
- Quand l'utiliser : tester plusieurs micro-affirmations liées à un même thème.
- Champs : "statements" = liste d'objets { "text", "answer" (booléen) }.
- Exemple :
  { "type": "k_prime", "instruction": "Pour chaque affirmation, indique Vrai ou Faux :",
    "statements": [
      { "text": "La mitochondrie produit l'énergie.", "answer": true },
      { "text": "Le noyau contient l'ADN.", "answer": true },
      { "text": "La membrane laisse tout passer.", "answer": false } ],
    "explanation": "La membrane est sélective." }
- Piège : 3 à 5 affirmations INDÉPENDANTES, chacune avec son propre "answer".
  L'élève doit avoir TOUTES les lignes justes.

────────────────────────────────────────────────────────────────────────────
5. cloze_test — Texte à trous
- Quand l'utiliser : compléter des mots-clés dans une phrase (langues, définitions).
- Champs : "text" avec des trous notés {{0}}, {{1}}… ; "answers" = liste, answers[i]
  étant la réponse du trou i.
- Exemple :
  { "type": "cloze_test", "instruction": "Complète le texte :",
    "text": "La photosynthèse produit du {{0}} et de l'{{1}}.",
    "answers": ["glucose", "oxygène"] }
- Piège : numérote les trous sans saut (0,1,2…) ; "answers" dans le MÊME ordre ;
  réponses courtes (1 à 3 mots), comparées en ignorant accents/casse.

────────────────────────────────────────────────────────────────────────────
6. matching — Appariement
- Quand l'utiliser : relier deux colonnes (organe→fonction, mot→traduction, date→événement).
- Champs : "pairs" = liste d'objets { "left", "right" } dans l'ordre CORRECT.
- Exemple :
  { "type": "matching", "instruction": "Associe chaque organe à sa fonction :",
    "pairs": [
      { "left": "Cœur", "right": "Pompe le sang" },
      { "left": "Poumon", "right": "Échange les gaz" },
      { "left": "Rein", "right": "Filtre le sang" } ] }
- Piège : donne les paires DANS LE BON APPARIEMENT (le frontend mélange l'affichage).
  Chaque "left" a un seul "right" ; 3 à 5 paires ; pas de doublon.

────────────────────────────────────────────────────────────────────────────
7. chrono_order — Remise en ordre
- Quand l'utiliser : remettre des étapes/événements en séquence (histoire, procédés).
- Champs : "items" (liste de textes, affichés mélangés) ; "correct_order" = liste
  des INDEX de "items" dans l'ordre attendu.
- Exemple :
  { "type": "chrono_order", "instruction": "Remets ces événements dans l'ordre :",
    "items": ["Indépendance du Mali", "Empire du Mali (Soundiata)", "Colonisation française"],
    "correct_order": [1, 2, 0] }
- Piège : "correct_order" contient des INDEX de "items", pas les textes eux-mêmes.

────────────────────────────────────────────────────────────────────────────
8. number_input — Réponse numérique
- Quand l'utiliser : une réponse chiffrée exacte (dénombrement, calcul simple).
- Champs : "answer" (nombre) ; "tolerance" (optionnel, écart accepté, défaut 0).
- Exemple :
  { "type": "number_input", "instruction": "Combien de régions le Mali compte-t-il (2023) ?",
    "answer": 19, "tolerance": 0 }
- Piège : "answer" est un nombre PUR (pas de texte ni d'unité). Mets une "tolerance"
  pour les résultats décimaux ou les mesures.

────────────────────────────────────────────────────────────────────────────
9. dynamic_formula — Formule à variables aléatoires
- Quand l'utiliser : un calcul paramétré, RÉGÉNÉRÉ par élève (anti-triche) — maths,
  physique, comptabilité.
- Champs : "formula_template" (l'équation, ex. "a + b") ; "variables" (un objet
  où chaque variable a { "min", "max", "step" }) ; "solution_formula" (la formule qui
  CALCULE la réponse à partir des variables) ; "expected_input" ("numeric") ;
  "correct_answer" (valeur témoin d'un tirage).
- RÈGLE PLACEHOLDERS — CRUCIAL : dans "instruction", CHAQUE variable DOIT apparaître
  entre accolades {nom} (ex. {a}, {b}). Elle sera remplacée par un nombre tiré au
  moment de l'affichage. N'écris JAMAIS la lettre nue sans accolades : sinon l'élève
  verrait la lettre (« a oranges ») au lieu d'un nombre (« 3 oranges ») — ce qui n'a
  AUCUN sens, surtout pour les jeunes niveaux. Les accolades ne servent QUE dans
  "instruction" ; "formula_template" et "solution_formula" gardent les noms nus (a, b).
- Exemple :
  { "type": "dynamic_formula",
    "instruction": "Un vendeur a {a} oranges et {b} oranges. Combien en a-t-il en tout ?",
    "formula_template": "a + b",
    "variables": { "a": {"min":1,"max":9,"step":1}, "b": {"min":1,"max":9,"step":1} },
    "solution_formula": "a + b", "expected_input": "numeric", "correct_answer": 8 }
- Piège : "solution_formula" DOIT être une vraie formule CALCULABLE à partir des
  variables (ex. "(c - b) / a"), jamais une constante. Choisis des "min"/"max"/"step"
  qui donnent un résultat propre, et un énoncé CONCRET (objets, fruits, billes…)
  adapté à l'âge. Le serveur recalcule la réponse par élève.

────────────────────────────────────────────────────────────────────────────
10. math_expression — Expression mathématique
- Quand l'utiliser : produire/transformer une expression algébrique (développer, factoriser).
- Champs : "correct_expression" (forme de référence) ; "accepted_equivalents" (liste
  de formes équivalentes acceptées).
- Exemple :
  { "type": "math_expression", "instruction": "Développe (x + 1)².",
    "correct_expression": "x^2 + 2*x + 1",
    "accepted_equivalents": ["x**2+2x+1", "1 + 2x + x^2"] }
- Piège : fournis TOUJOURS quelques "accepted_equivalents" (ordre des termes, ^ vs **)
  pour aider la comparaison. Évite les expressions trop ouvertes à interprétation.

────────────────────────────────────────────────────────────────────────────
11. spot_the_bug — Trouver le bug
- Quand l'utiliser : identifier la ligne fautive d'un extrait de code (informatique).
- Champs : "language" ; "code" (liste de lignes) ; "buggy_line" (index 0-based de la
  ligne erronée) ; "correct_fix" (optionnel, la correction, affichée en explication).
- Exemple :
  { "type": "spot_the_bug", "instruction": "Quelle ligne contient l'erreur ?",
    "language": "python",
    "code": ["def moyenne(notes):", "    total = 0", "    for n in notes:",
             "        total = n", "    return total / len(notes)"],
    "buggy_line": 3, "correct_fix": "total += n" }
- Piège : UNE seule ligne fautive, clairement identifiable ; "buggy_line" est un
  index 0-based dans "code".

────────────────────────────────────────────────────────────────────────────
12. parsons_puzzle — Puzzle de code (Parsons)
- Quand l'utiliser : reconstituer un code en ORDRE et INDENTATION (programmation).
- Champs : "language" ; "lines" = liste de { "id", "text", "correct_indent" (niveau,
  0 = sans indentation) } ; "correct_sequence" = liste des "id" dans l'ordre correct.
- Exemple :
  { "type": "parsons_puzzle", "instruction": "Remets ce code Python dans l'ordre :",
    "language": "python",
    "lines": [
      { "id": "L1", "text": "def carre(x):", "correct_indent": 0 },
      { "id": "L2", "text": "return x * x", "correct_indent": 1 },
      { "id": "L3", "text": "print(carre(5))", "correct_indent": 0 } ],
    "correct_sequence": ["L1", "L2", "L3"] }
- Piège : "correct_sequence" liste des "id" (pas des textes) ; "correct_indent"
  cohérent avec la syntaxe. Réservé au code.

────────────────────────────────────────────────────────────────────────────
13. odd_one_out — L'intrus
- Quand l'utiliser : trouver l'élément qui n'appartient pas à un groupe.
- Champs : "items" (liste de textes) ; "odd_index" (index 0-based de l'intrus).
- Exemple :
  { "type": "odd_one_out", "instruction": "Quel mot est l'intrus ?",
    "items": ["Bambara", "Peul", "Songhaï", "Wolof"], "odd_index": 3,
    "explanation": "Le wolof est surtout parlé au Sénégal, pas au Mali." }
- Piège : UN seul intrus, avec un critère commun clair aux autres items ;
  "odd_index" est 0-based.

────────────────────────────────────────────────────────────────────────────

Tu utilises CES 13 TYPES UNIQUEMENT — jamais les types reportés (image, audio,
correction par IA, etc.).

- RAPPEL STRICT : n'utilise JAMAIS de type reporté (ceux dépendant d'image, d'audio,
  ou de correction par IA). Tu ne produis que les 13 types du catalogue ci-dessus.

GÉNÉRATION DE L'EXAMEN
- L'examen couvre les concepts de la leçon ; chaque question porte un "concept_id".
- Les questions sont GÉNÉRÉES SPÉCIFIQUEMENT pour l'examen : ne reprends PAS les
  quiz des concepts à l'identique. Reformule, teste les mêmes notions autrement —
  l'examen ÉVALUE, il ne fait pas réciter.
- "pass_mark" : 0.6 par défaut.
- "duration" : durée en secondes, environ 60 s par question.
- Les questions d'examen utilisent les mêmes types de quiz (catalogue ci-dessus).

CHAMPS color ET guide
Tu complètes deux champs de mise en forme de la leçon :
- "color" : une couleur d'accent (hex) cohérente avec la matière.
- "guide" : le nom d'un personnage fil rouge malien (ex. « Cyto », « Numa »). Ce
  même personnage pourra être réutilisé par l'histoire de la leçon.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
- Exactement DEUX blocs, dans cet ordre : <reflexion>…</reflexion> puis <json>…</json>.
- Aucun texte hors de ces deux blocs. Aucun markdown.
- Le contenu de <json> est un objet JSON VALIDE et STRICT, de la forme :
{
  "color": "#10B981",
  "guide": "Cyto",
  "concepts": [
    {
      "id": "transport_membranaire",
      "name": "Le transport membranaire",
      "order": 3,
      "passes": 2,
      "quiz": [ /* questions, types du catalogue, chacune avec pass_index */ ]
    }
  ],
  "exam": {
    "pass_mark": 0.6,
    "duration": 600,
    "questions": [ /* questions taguées concept_id, types du catalogue */ ]
  }
}
- Le premier caractère du bloc <json> est { et le dernier est }.

LEÇON À TRAITER
Titre   : {lesson_title}
Résumé  : {lesson_summary}
Source  :
{lesson_source}"""


def call_noyau(lesson_title: str, lesson_summary: str, source, cost_sink: list = None) -> dict:
    """Appel B1 « Noyau » : une leçon → { color, guide, concepts[], exam }.

    lesson_title / lesson_summary : issus de l'Architecte (texte).
    source : portion de document de la leçon — str (texte) OU list de blocs image
             base64 (sortie de extract_content_from_file), comme call_architect.
    Retourne le noyau validé. Lève ValueError si le JSON ou les passes sont invalides.
    NE TOUCHE PAS à l'existant."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Injections texte communes (titre + résumé), toujours.
    base = (NOYAU_PROMPT
            .replace('{lesson_title}', lesson_title)
            .replace('{lesson_summary}', lesson_summary))

    if isinstance(source, str):
        user_content = [{'type': 'text', 'text': base.replace('{lesson_source}', source)}]
    else:
        user_content = [
            {'type': 'image',
             'source': {'type': 'base64', 'media_type': img['media_type'], 'data': img['data']}}
            for img in source
        ]
        prompt_imgs = base.replace('{lesson_source}', 'lis les images fournies ci-dessus.')
        user_content.append({'type': 'text', 'text': prompt_imgs})

    start = time.time()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=NOYAU_MAX_TOKENS,
        messages=[{'role': 'user', 'content': user_content}],
    )
    cost = (
        Decimal(response.usage.input_tokens) / 1_000_000 * CLAUDE_INPUT_COST_PER_M
        + Decimal(response.usage.output_tokens) / 1_000_000 * CLAUDE_OUTPUT_COST_PER_M
    )
    logger.info(
        'Noyau B1: %d in / %d out / $%.6f / %.1fs',
        response.usage.input_tokens, response.usage.output_tokens, cost, time.time() - start,
    )

    if cost_sink is not None:
        cost_sink.append(cost)

    return _parse_noyau(response.content[0].text)


def _parse_noyau(raw: str) -> dict:
    """Extrait le bloc <json>…</json> (IGNORE <reflexion>), parse en résilient,
    valide la forme { color, guide, concepts[], exam } et les invariants des passes."""
    # 1. Extraire le <json> ; fallback sur le brut si les balises manquent.
    m = re.search(r'<json>(.*?)</json>', raw, re.S)
    json_str = m.group(1) if m else raw

    # 2. Parse résilient (réutilise A.1).
    data = _loads_json_resilient(json_str)

    # 3. Forme attendue.
    required = ['color', 'guide', 'concepts', 'exam']
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Noyau B1 incomplet, clés manquantes: {missing}")
    if not isinstance(data['concepts'], list) or not data['concepts']:
        raise ValueError("Noyau B1: 'concepts' vide ou invalide")
    if not isinstance(data['exam'], dict) or 'questions' not in data['exam']:
        raise ValueError("Noyau B1: 'exam.questions' manquant")

    # 4. Invariants des passes (§3.3).
    _validate_passes(data['concepts'])
    return data


def _validate_passes(concepts: list) -> None:
    """§3.3 : 1 ≤ passes ≤ 4 ; pass_index ∈ [0, passes-1] ; aucune passe vide."""
    for c in concepts:
        cid = c.get('id', '?')
        passes = c.get('passes', 1)
        if not isinstance(passes, int) or not (1 <= passes <= 4):
            raise ValueError(f"concept '{cid}': passes invalide ({passes}) — attendu 1..4")
        quiz = c.get('quiz', [])
        if not isinstance(quiz, list) or not quiz:
            raise ValueError(f"concept '{cid}': aucun quiz")
        seen = set()
        for q in quiz:
            pi = q.get('pass_index', 0)
            if not isinstance(pi, int) or not (0 <= pi <= passes - 1):
                raise ValueError(f"concept '{cid}': pass_index {pi} hors [0,{passes - 1}]")
            seen.add(pi)
        vides = set(range(passes)) - seen
        if vides:
            raise ValueError(f"concept '{cid}': passe(s) vide(s) {sorted(vides)}")


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Temps 2 / Appels B2 « Lecture » + B3 « Histoire » (A.3)
# ───────────────────────────────────────────────────────────────────────────────
# Additif, en parallèle de l'existant et des codes A.1/A.2. B2 et B3 utilisent le
# JSON DIRECT (pas de <reflexion> à extraire, contrairement à B1) : on parse en
# résilient directement. LECTURE_PROMPT = PORTAL_V2_SPEC §4.9 ; HISTOIRE_PROMPT =
# §4.10. B3 reçoit le guide et les concepts produits par B1.
# ═══════════════════════════════════════════════════════════════════════════════

# Le reading peut être long : plusieurs sections × blocs variés (p+simple, def,
# callout, key, example, reflect, warn, check) + glossaire. 12k couvre une lecture
# riche sans la lourdeur de B1 (pas de quiz × concepts). Facturé sur le réel.
LECTURE_MAX_TOKENS = 12_000

LECTURE_PROMPT = """Tu es un concepteur pédagogique malien expert, spécialiste de la RÉDACTION
pédagogique claire. Tu écris pour des élèves maliens qui lisent sur un téléphone :
phrases nettes, ton chaleureux, exemples du quotidien malien (marché de Bamako,
francs CFA, mangues, transport, famille, champs, boutique, mosquée).

TA MISSION
Tu reçois la source d'UNE seule leçon (son titre, son résumé, et la portion de
document correspondante). Tu génères UNIQUEMENT le CONTENU DE LECTURE de cette
leçon (le champ « reading ») : un texte structuré, clair et agréable à lire sur
mobile.

Tu ne génères PAS les quiz, ni l'histoire, ni l'examen : ils sont produits par
d'autres appels. Concentre-toi sur la lecture.

STRUCTURE À PRODUIRE
- "title"     : le titre de la lecture.
- "direction" : le sens de lecture, fourni ci-dessous ({direction}) — « ltr » ou « rtl ».
- "terms"     : un glossaire { mot: définition }. Chaque mot devient cliquable dans
                le texte ; définitions COURTES.
- "sections"  : une liste de sections, chacune { "id", "title", "blocks" }.

LES 8 TYPES DE BLOCS (champ "type" de chaque bloc)
- "p"       : paragraphe — { "text", "simple"? }.  "simple" est OPTIONNEL : une
              reformulation plus simple, à n'ajouter QUE si le paragraphe est difficile.
- "def"     : définition — { "term", "text" }.
- "callout" : encart — { "icon", "label", "text" } (ex. label « Le saviez-vous »).
- "key"     : points clés — { "items": [ ... ] } (liste de phrases courtes).
- "example" : exemple concret — { "text" }.
- "reflect" : invite à réfléchir — { "prompt" } (une question ouverte, sans réponse).
- "warn"    : mise en garde — { "text" } (piège fréquent, confusion à éviter).
- "check"   : mini-quiz DANS la lecture — { "variant", "question", ..., "explanation" } :
                • variant "tf"  : ajoute "answer" (booléen true/false) ;
                • variant "qcm" : ajoute "options" (liste) et "answer" (index de la
                  bonne option).
              "explanation" justifie la bonne réponse.

PRINCIPES DE RÉDACTION
- Sois clair et progressif ; adapte le vocabulaire au niveau détecté dans la source.
- ALTERNE les types de blocs pour rythmer la lecture — jamais 10 paragraphes
  d'affilée. Entrelace définitions, exemples, points clés, encarts, vérifications.
- Glossaire "terms" : inclus les mots techniques importants, avec des définitions
  brèves et accessibles.
- Version "simple" d'un "p" : seulement quand le paragraphe est DIFFICILE, pas
  systématiquement.
- Insère QUELQUES blocs "check" répartis dans la lecture, pour vérifier la
  compréhension en cours de route.
- Ancre les explications dans le quotidien malien quand c'est pertinent.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
- Tu réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant, aucun texte
  après, aucun bloc markdown. Le premier caractère est { et le dernier est }.
- Forme exacte :
{
  "reading": {
    "title": "La membrane plasmique",
    "direction": "ltr",
    "terms": {
      "membrane plasmique": "La fine enveloppe qui entoure la cellule et contrôle ce qui entre et sort.",
      "transport actif": "Le passage d'une molécule à travers la membrane qui consomme de l'énergie (ATP)."
    },
    "sections": [
      {
        "id": "s1",
        "title": "La frontière de la cellule",
        "blocks": [
          { "type": "p", "text": "Chaque cellule est entourée d'une membrane plasmique…",
            "simple": "Chaque cellule a une membrane autour d'elle." },
          { "type": "def", "term": "membrane plasmique", "text": "la fine enveloppe qui entoure la cellule." },
          { "type": "callout", "icon": "spark", "label": "Le saviez-vous",
            "text": "La membrane est si fine qu'il en faudrait des milliers pour égaler une feuille de papier." },
          { "type": "check", "variant": "tf",
            "question": "La membrane laisse tout passer sans distinction.",
            "answer": false, "explanation": "Elle est sélective : elle choisit ce qui passe." }
        ]
      },
      {
        "id": "s2",
        "title": "Comment les choses entrent ?",
        "blocks": [
          { "type": "key", "items": ["L'eau passe par osmose.", "Le glucose passe par une protéine."] },
          { "type": "example", "text": "Le glucose, trop gros, utilise une protéine de transport." },
          { "type": "warn", "text": "Ne confonds pas osmose (sans énergie) et transport actif (avec énergie)." },
          { "type": "reflect", "prompt": "Pourquoi une barrière sélective plutôt qu'un mur fermé ?" },
          { "type": "check", "variant": "qcm",
            "question": "Qu'est-ce qui fait passer le glucose ?",
            "options": ["La bicouche seule", "Une protéine de transport", "Rien"],
            "answer": 1, "explanation": "Le glucose est trop gros : il passe par une protéine." }
        ]
      }
    ]
  }
}

LEÇON À TRAITER
Sens de lecture : {direction}
Titre   : {lesson_title}
Résumé  : {lesson_summary}
Source  :
{lesson_source}"""


def call_lecture(lesson_title: str, lesson_summary: str, source, direction: str = 'ltr',
                 cost_sink: list = None) -> dict:
    """Appel B2 « Lecture » : une leçon → { reading: { title, direction, terms{}, sections[] } }.

    source : str (texte) OU list de blocs image base64 (comme call_noyau).
    Retourne la lecture validée. Lève ValueError si la forme est invalide.
    NE TOUCHE PAS à l'existant."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    base = (LECTURE_PROMPT
            .replace('{direction}', direction)
            .replace('{lesson_title}', lesson_title)
            .replace('{lesson_summary}', lesson_summary))

    if isinstance(source, str):
        user_content = [{'type': 'text', 'text': base.replace('{lesson_source}', source)}]
    else:
        user_content = [
            {'type': 'image',
             'source': {'type': 'base64', 'media_type': img['media_type'], 'data': img['data']}}
            for img in source
        ]
        prompt_imgs = base.replace('{lesson_source}', 'lis les images fournies ci-dessus.')
        user_content.append({'type': 'text', 'text': prompt_imgs})

    start = time.time()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=LECTURE_MAX_TOKENS,
        messages=[{'role': 'user', 'content': user_content}],
    )
    cost = (
        Decimal(response.usage.input_tokens) / 1_000_000 * CLAUDE_INPUT_COST_PER_M
        + Decimal(response.usage.output_tokens) / 1_000_000 * CLAUDE_OUTPUT_COST_PER_M
    )
    logger.info(
        'Lecture B2: %d in / %d out / $%.6f / %.1fs',
        response.usage.input_tokens, response.usage.output_tokens, cost, time.time() - start,
    )

    if cost_sink is not None:
        cost_sink.append(cost)

    return _parse_lecture(response.content[0].text)


def _parse_lecture(raw: str) -> dict:
    """JSON résilient direct (pas de <json> à extraire), valide { reading: { title, sections[] } }."""
    data = _loads_json_resilient(raw)
    reading = data.get('reading')
    if not isinstance(reading, dict):
        raise ValueError("Lecture B2: clé 'reading' manquante ou invalide")
    if 'title' not in reading:
        raise ValueError("Lecture B2: 'reading.title' manquant")
    if not isinstance(reading.get('sections'), list) or not reading['sections']:
        raise ValueError("Lecture B2: 'reading.sections' vide ou invalide")
    return data


# Une seule histoire : scene + 2-3 personnages + ~8-15 steps courts. Plus léger que
# la lecture et que B1. 8k est largement suffisant pour un récit complet.
HISTOIRE_MAX_TOKENS = 8_000

HISTOIRE_PROMPT = """Tu es un concepteur pédagogique malien expert, spécialiste de la NARRATION
pédagogique : tu RACONTES pour faire comprendre. Tu crées des personnages
attachants et des situations du quotidien malien (marché de Bamako, francs CFA,
mangues, transport, famille, champs, boutique, mosquée).

TA MISSION
Tu reçois la source d'UNE leçon, la LISTE DES CONCEPTS de cette leçon, et le nom
du personnage GUIDE. Tu génères UNE histoire interactive (le champ « story ») qui
fait VIVRE les notions de la leçon : l'élève comprend en agissant, pas en regardant.

Tu ne génères PAS les quiz, ni le texte de lecture, ni l'examen : ils sont produits
par d'autres appels. Concentre-toi sur l'histoire.

COHÉRENCE AVEC LE RESTE DE LA LEÇON (important)
- Réutilise le personnage GUIDE fourni ({guide}) comme personnage CENTRAL de
  l'histoire (il fait partie de "characters").
- L'histoire doit ILLUSTRER les concepts fournis ci-dessous. Sur les steps qui
  testent ou mettent en scène une notion précise, ajoute un champ optionnel
  "concept_ref" portant l'"id" du concept concerné (issu de la liste fournie).

STRUCTURE À PRODUIRE
- "scene"      : { "name", "c1", "c2" } — nom de la scène + 2 couleurs d'ambiance (hex).
- "characters" : liste d'objets { "id", "name", "role", "color", "side" }
                 ("side" vaut "left" ou "right" ; "color" en hex ; le GUIDE en fait partie).
- "steps"      : la liste du déroulé, composée des 6 types ci-dessous.

LES 6 TYPES DE STEP (champ "type")
- "narration" : { "text" } — décor/atmosphère, SANS personnage.
- "npc"       : { "who", "text" } — réplique d'un personnage ("who" = "id" d'un character).
- "choice"    : { "prompt", "options": [ { "label", "correct", "reply" } ] } — choix
                narratif. UNE option a "correct": true ; "reply" est la réponse du
                personnage à chaque option.
- "input"     : { "prompt", "answers": [ ... ], "hint", "ok" } — saisie libre.
                "answers" = réponses acceptées (comparées en ignorant accents/casse) ;
                "hint" = indice ; "ok" = message quand c'est juste.
- "tokens"    : { "prompt", "tokens": [ ... ], "solution": [ ... ], "ok" } — remettre
                des éléments dans l'ordre. "solution" = les "tokens" dans le bon ordre.
- "blank"     : { "prompt", "parts": [ ... ], "options": [ ... ], "answer", "ok" } —
                compléter une phrase à trou. "parts" encadre le trou (avant/après) ;
                "answer" est la bonne option.
Tout step peut porter, en plus, un "concept_ref" optionnel (id d'un concept).

PRINCIPES NARRATIFS
- Écris une VRAIE petite histoire avec un fil : début, péripétie, résolution — pas
  une suite de questions déguisées.
- 2 à 3 personnages maximum, dont le GUIDE.
- ALTERNE narration / dialogue / interactions pour rythmer.
- Les interactions testent la compréhension des concepts EN SITUATION.
- Ancre l'histoire dans le quotidien malien (lieux, noms, objets).
- Ton chaleureux, adapté au niveau détecté dans la source.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
- Tu réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant, aucun texte
  après, aucun bloc markdown. Le premier caractère est { et le dernier est }.
- Forme exacte :
{
  "story": {
    "scene": { "name": "Au marché de Bamako", "c1": "#F97316", "c2": "#BE123C" },
    "characters": [
      { "id": "awa",  "name": "Awa",   "role": "Guide",    "color": "#F97316", "side": "left" },
      { "id": "moussa","name": "Moussa","role": "Vendeur",  "color": "#22D3EE", "side": "right" }
    ],
    "steps": [
      { "type": "narration", "text": "Marché de Bamako, au lever du jour. Awa accompagne son petit frère faire les courses." },
      { "type": "npc", "who": "awa", "text": "Bonjour Moussa ! Trois mangues, s'il te plaît." },
      { "type": "npc", "who": "moussa", "text": "Chaque mangue coûte 150 francs. Voyons le total…" },
      { "type": "input", "prompt": "Combien coûtent 3 mangues à 150 F l'unité ?",
        "answers": ["450", "450 f", "450 francs"], "hint": "150 × 3.",
        "ok": "450 francs, exact !", "concept_ref": "multiplication" },
      { "type": "choice", "prompt": "Awa paie avec 500 F. Que doit rendre Moussa ?", "options": [
          { "label": "50 francs", "correct": true,  "reply": "Oui : 500 − 450 = 50 F." },
          { "label": "150 francs", "correct": false, "reply": "Non, ça c'est le prix d'une mangue." }
        ], "concept_ref": "soustraction" },
      { "type": "npc", "who": "moussa", "text": "Voilà tes 3 mangues et 50 francs. À bientôt !" }
    ]
  }
}

ENTRÉES
Guide (personnage central) : {guide}
Concepts à illustrer (id — name) :
{concepts_list}
Titre   : {lesson_title}
Résumé  : {lesson_summary}
Source  :
{lesson_source}"""


def call_histoire(lesson_title: str, lesson_summary: str, source,
                  guide: str, concepts, cost_sink: list = None) -> dict:
    """Appel B3 « Histoire » : une leçon (+ guide + concepts de B1) →
    { story: { scene, characters[], steps[] } }.

    concepts : la LISTE brute de concepts de B1 (ex. noyau['concepts']). La fonction
    la formate elle-même en « id — name » par ligne (responsabilité de la fonction,
    pas de l'appelant) avant injection à la place de {concepts_list}.
    source : str (texte) OU list de blocs image base64.
    NE TOUCHE PAS à l'existant."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Format interne « id — name » par ligne, défensif sur les clés manquantes.
    concepts_list = "\n".join(
        f"{c.get('id', '?')} — {c.get('name', '?')}" for c in (concepts or [])
    )

    base = (HISTOIRE_PROMPT
            .replace('{guide}', guide)
            .replace('{concepts_list}', concepts_list)
            .replace('{lesson_title}', lesson_title)
            .replace('{lesson_summary}', lesson_summary))

    if isinstance(source, str):
        user_content = [{'type': 'text', 'text': base.replace('{lesson_source}', source)}]
    else:
        user_content = [
            {'type': 'image',
             'source': {'type': 'base64', 'media_type': img['media_type'], 'data': img['data']}}
            for img in source
        ]
        prompt_imgs = base.replace('{lesson_source}', 'lis les images fournies ci-dessus.')
        user_content.append({'type': 'text', 'text': prompt_imgs})

    start = time.time()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=HISTOIRE_MAX_TOKENS,
        messages=[{'role': 'user', 'content': user_content}],
    )
    cost = (
        Decimal(response.usage.input_tokens) / 1_000_000 * CLAUDE_INPUT_COST_PER_M
        + Decimal(response.usage.output_tokens) / 1_000_000 * CLAUDE_OUTPUT_COST_PER_M
    )
    logger.info(
        'Histoire B3: %d in / %d out / $%.6f / %.1fs',
        response.usage.input_tokens, response.usage.output_tokens, cost, time.time() - start,
    )

    if cost_sink is not None:
        cost_sink.append(cost)

    return _parse_histoire(response.content[0].text)


def _parse_histoire(raw: str) -> dict:
    """JSON résilient direct, valide { story: { scene, characters[], steps[] } }."""
    data = _loads_json_resilient(raw)
    story = data.get('story')
    if not isinstance(story, dict):
        raise ValueError("Histoire B3: clé 'story' manquante ou invalide")
    if not isinstance(story.get('scene'), dict):
        raise ValueError("Histoire B3: 'story.scene' manquant")
    if not isinstance(story.get('characters'), list) or not story['characters']:
        raise ValueError("Histoire B3: 'story.characters' vide ou invalide")
    if not isinstance(story.get('steps'), list) or not story['steps']:
        raise ValueError("Histoire B3: 'story.steps' vide ou invalide")
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Évaluation serveur des 13 types de quiz (A.5)
# ───────────────────────────────────────────────────────────────────────────────
# Additif, en parallèle de l'existant (l'ancien evaluate_answer v1 / 5 types n'est
# PAS touché). Chaque règle suit §3 — Partie 2 « B. Évaluation serveur » au mot.
# 100 % serveur, instantané, sans IA, défensif (toute donnée malformée → False ;
# type inconnu → False).
# ═══════════════════════════════════════════════════════════════════════════════

import ast as _ast
import operator as _op

# Garde d'import : la voie symbolique (math_expression) s'active automatiquement si
# sympy est présent ; sinon on retombe sur normalisation + accepted_equivalents.
try:
    import sympy as _sympy
    _HAS_SYMPY = True
except ImportError:  # pragma: no cover
    _sympy = None
    _HAS_SYMPY = False


# ── Évaluateur arithmétique SÛR (jamais eval() Python) ─────────────────────────
_ARITH_OPS = {
    _ast.Add: _op.add, _ast.Sub: _op.sub, _ast.Mult: _op.mul,
    _ast.Div: _op.truediv, _ast.Pow: _op.pow, _ast.Mod: _op.mod,
    _ast.USub: _op.neg, _ast.UAdd: _op.pos,
}


def _safe_eval_arith(expr: str, values: dict):
    """Évalue une expression arithmétique avec des variables, SANS eval() Python.

    Seuls sont autorisés : constantes numériques, noms de variables (résolus depuis
    `values`), et les opérateurs + - * / ** % et l'unaire ±. Tout le reste (appels
    de fonction, attributs, noms inconnus) lève ValueError → sécurité."""
    tree = _ast.parse(expr, mode='eval')

    def ev(node):
        if isinstance(node, _ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"constante interdite : {node.value!r}")
        if isinstance(node, _ast.Name):
            if node.id in values:
                return values[node.id]
            raise ValueError(f"variable inconnue : {node.id}")
        if isinstance(node, _ast.BinOp) and type(node.op) in _ARITH_OPS:
            return _ARITH_OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, _ast.UnaryOp) and type(node.op) in _ARITH_OPS:
            return _ARITH_OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"noeud interdit : {type(node).__name__}")

    return ev(tree.body)


# ── Helpers par type non trivial ───────────────────────────────────────────────
def _eval_matching(quiz: dict, student) -> bool:
    """matching : student[i] = index right choisi pour left[i] (index dans pairs[]).
    Correct ssi chaque left pointe son right d'origine, soit student == [0,1,…,n-1]."""
    pairs = quiz.get('pairs', [])
    return list(student) == list(range(len(pairs)))


def _eval_parsons(quiz: dict, student) -> bool:
    """parsons_puzzle : ordre ET indentation.
    student = [{'id', 'indent'}, …] dans l'ordre soumis."""
    seq = quiz.get('correct_sequence', [])
    indent_by_id = {l['id']: l.get('correct_indent') for l in quiz.get('lines', [])}
    if [x['id'] for x in student] != list(seq):
        return False
    return all(x.get('indent') == indent_by_id.get(x['id']) for x in student)


def _eval_dynamic_formula(quiz: dict, student_answer, context) -> bool:
    """dynamic_formula (anti-triche) : recalcule la réponse attendue serveur.

    student_answer = UNIQUEMENT le nombre saisi par l'élève.
    context = source serveur de confiance : {'variables': {nom: nombre}} — le tirage
    stocké côté serveur quand la question a été servie (JAMAIS rempli depuis le client).
    Sans context/variables, on ne peut pas évaluer en sécurité → False."""
    if not isinstance(context, dict) or 'variables' not in context:
        return False
    expected = _safe_eval_arith(quiz['solution_formula'], context['variables'])
    tol = quiz.get('tolerance', 0)
    return abs(float(student_answer) - float(expected)) <= tol


def _eval_math_expression(quiz: dict, student) -> bool:
    """math_expression : symbolique si sympy dispo, sinon normalisation + équivalents."""
    cands = {quiz.get('correct_expression', '')}
    cands.update(quiz.get('accepted_equivalents', []))
    student = str(student)

    if _HAS_SYMPY:
        try:
            s = _sympy.sympify(student.replace('^', '**'))
            for c in cands:
                if _sympy.simplify(s - _sympy.sympify(c.replace('^', '**'))) == 0:
                    return True
        except Exception:
            pass  # filet : on retombe sur la normalisation

    def _norm(e: str) -> str:
        return str(e).lower().replace('^', '**').replace(' ', '')

    return _norm(student) in {_norm(c) for c in cands}


def evaluate_answer_v2(quiz: dict, student_answer, context: dict = None) -> bool:
    """Évalue la réponse de l'élève pour les 13 types v2 (§3 — Partie 2). Retourne bool.

    student_answer : UNIQUEMENT ce que l'élève saisit/sélectionne. Formats par type :
      - mcq_single / spot_the_bug / odd_one_out : int (un index)
      - mcq_multiple : list[int]            - true_false : bool
      - k_prime : list[bool] (1 par statement, même ordre)
      - cloze_test : list[str] (1 par trou, même ordre)
      - matching : list[int] (student[i] = index right choisi pour left[i])
      - chrono_order : list[int]            - number_input : int|float
      - dynamic_formula : int|float (le nombre saisi SEUL — les variables viennent de context)
      - math_expression : str               - parsons_puzzle : list[{'id','indent'}]

    context : source de vérité SERVEUR, optionnelle, JAMAIS remplie depuis le client.
      Seul `dynamic_formula` l'utilise : context = {'variables': {…}} = le tirage stocké
      côté serveur (produit par draw_dynamic_formula). Les 12 autres types l'ignorent.

    Défensif : toute donnée malformée ou type inconnu → False. Ne touche pas à
    l'ancien evaluate_answer (v1)."""
    qtype = quiz.get('type')
    try:
        if qtype == 'mcq_single':
            return int(student_answer) == quiz['answer_index']

        if qtype == 'mcq_multiple':
            return set(student_answer) == set(quiz['answer_indices'])

        if qtype == 'true_false':
            return bool(student_answer) == bool(quiz['answer'])

        if qtype == 'k_prime':
            statements = quiz['statements']
            if len(student_answer) != len(statements):
                return False
            return all(bool(student_answer[i]) == bool(s['answer'])
                       for i, s in enumerate(statements))

        if qtype == 'cloze_test':
            answers = quiz['answers']
            if len(student_answer) != len(answers):
                return False
            return all(normalize_text(str(student_answer[i])) == normalize_text(str(answers[i]))
                       for i in range(len(answers)))

        if qtype == 'matching':
            return _eval_matching(quiz, student_answer)

        if qtype == 'chrono_order':
            return list(student_answer) == list(quiz['correct_order'])

        if qtype == 'number_input':
            tol = quiz.get('tolerance', 0)
            return abs(float(student_answer) - float(quiz['answer'])) <= tol

        if qtype == 'dynamic_formula':
            return _eval_dynamic_formula(quiz, student_answer, context)

        if qtype == 'math_expression':
            return _eval_math_expression(quiz, student_answer)

        if qtype == 'spot_the_bug':
            return int(student_answer) == quiz['buggy_line']

        if qtype == 'parsons_puzzle':
            return _eval_parsons(quiz, student_answer)

        if qtype == 'odd_one_out':
            return int(student_answer) == quiz['odd_index']

    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return False

    return False  # type inconnu → défensif


def draw_dynamic_formula(quiz: dict) -> dict:
    """Tirage par élève pour dynamic_formula (utilitaire — branché en Phase B).

    Tire des valeurs aléatoires dans `variables` (ranges min/max/step), substitue dans
    l'énoncé, recalcule la réponse attendue. Retourne :
      { 'variables': {nom: nombre},   # À STOCKER côté serveur, reviendra via context
        'statement' : <énoncé personnalisé>,
        'correct_answer': <recalculé> }

    Intégration runtime complète (hors A.5) : il faut persister `variables` quand la
    question est servie (ex. état de session / ExamAttempt, Phase B) puis les
    re-fournir à evaluate_answer_v2 via `context={'variables': …}` à la correction.
    Les variables ne doivent JAMAIS transiter par le client (anti-triche)."""
    variables = {}
    for name, spec in quiz.get('variables', {}).items():
        lo, hi = spec['min'], spec['max']
        step = spec.get('step', 1)
        n = int((hi - lo) / step)
        variables[name] = lo + random.randint(0, n) * step

    statement = quiz.get('instruction', '')
    for name, val in variables.items():
        statement = statement.replace('{' + name + '}', str(val))

    correct_answer = _safe_eval_arith(quiz['solution_formula'], variables)
    return {'variables': variables, 'statement': statement, 'correct_answer': correct_answer}


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Orchestration des 3 appels (A.4, §4.6)
# ───────────────────────────────────────────────────────────────────────────────
# Additif. Assemble call_noyau (B1) + call_lecture (B2) + call_histoire (B3) en
# UNE leçon finale (§3.1). N'altère PAS le pipeline v1 (generate_lesson_with_ai).
# Ordre §4.6 : B1 d'abord (ses concepts alimentent B3), puis B2 puis B3 (séquentiel
# pour l'instant ; B2/B3 sont indépendants → parallélisables plus tard sans changer
# la signature). Fallback par bloc : 1 rejeu isolé, blocs réussis jamais reperdus.
# ═══════════════════════════════════════════════════════════════════════════════

# Pause avant l'unique rejeu d'un bloc : si l'échec est un 529/500 transitoire (API
# surchargée), rejouer immédiatement retomberait sur la même surcharge. Une courte
# pause laisse l'API respirer. Pas un backoff complexe — juste un souffle.
BLOCK_RETRY_DELAY = 2  # secondes


class LessonBlockError(Exception):
    """Un bloc de génération (B1/B2/B3) a échoué malgré 1 rejeu.

    .block   : 'B1' | 'B2' | 'B3' — pour que l'appelant sache QUOI régénérer.
    .cause   : l'exception d'origine.
    .partial : { 'noyau'?, 'lecture'?, 'histoire'? } — les blocs DÉJÀ réussis, pour
               régénérer le seul bloc manquant sans tout refaire (utile en cas
               d'outage API)."""

    def __init__(self, block: str, cause: Exception, partial: dict = None):
        self.block = block
        self.cause = cause
        self.partial = partial or {}
        super().__init__(f"Bloc {block} a échoué après rejeu : {cause}")


def _run_block(name: str, fn, partial: dict):
    """Exécute un bloc de génération ; en cas d'échec, le REJOUE UNE FOIS (seul).

    `partial` = les blocs déjà réussis (jamais retouchés). Une courte pause précède
    le rejeu (cf. BLOCK_RETRY_DELAY) pour absorber un 529/500 transitoire. Si le
    rejeu échoue aussi, lève LessonBlockError(name) en y attachant `partial`."""
    try:
        return fn()
    except Exception as e1:
        logger.warning('Génération bloc %s : échec, rejeu unique dans %ds… (%s)',
                       name, BLOCK_RETRY_DELAY, e1)
        time.sleep(BLOCK_RETRY_DELAY)  # laisse l'API respirer avant le rejeu
        try:
            return fn()
        except Exception as e2:
            raise LessonBlockError(name, e2, partial) from e2


def _assemble_lesson(lesson_meta: dict, results: dict) -> dict:
    """Fusionne les 3 sorties dans l'objet leçon final (§3.1), provenance §4.6 stricte."""
    noyau, lecture, histoire = results['noyau'], results['lecture'], results['histoire']
    return {
        'id':        lesson_meta['id'],                    # serveur (slug Architecte)
        'title':     lesson_meta['title'],                 # Architecte
        'subject':   lesson_meta.get('subject'),           # Architecte
        'direction': lesson_meta.get('direction', 'ltr'),  # Architecte
        'color':     noyau['color'],                       # B1
        'guide':     noyau['guide'],                       # B1
        'concepts':  noyau['concepts'],                    # B1
        'exam':      noyau['exam'],                        # B1
        'reading':   lecture['reading'],                   # B2
        'story':     histoire['story'],                    # B3
    }


def generate_lesson_v2(lesson_meta: dict, source, cost_sink: list = None) -> dict:
    """Orchestre la génération complète d'UNE leçon v2 (§4.6).

    lesson_meta : la leçon issue de l'Architecte — { id, title, summary, subject,
                  direction } (subject/direction du niveau unité ; id/title/summary
                  de la leçon).
    source : la portion de document de la leçon (str OU list de blocs image base64).
    cost_sink : liste optionnelle où B1/B2/B3 ajoutent leur coût (Decimal). Forwardé
                tel quel ; None → aucun coût collecté. Le RETOUR ne change pas (objet
                §3.1 pur) : le coût remonte par cost_sink, pas par la valeur de retour.

    Retourne l'objet leçon final (§3.1). Lève LessonBlockError si un bloc échoue 2×
    (l'erreur porte le bloc fautif + les blocs déjà réussis dans .partial).
    NE TOUCHE PAS au pipeline v1 (generate_lesson_with_ai)."""
    title = lesson_meta['title']
    summary = lesson_meta['summary']
    direction = lesson_meta.get('direction', 'ltr')
    results = {}  # accumule les blocs réussis → jamais reperdus

    # 1. B1 d'abord (ses concepts alimentent B3).
    results['noyau'] = _run_block(
        'B1', lambda: call_noyau(title, summary, source, cost_sink=cost_sink), results)

    # 2. B2 puis 3. B3 (séquentiel ; indépendants → parallélisables plus tard).
    results['lecture'] = _run_block(
        'B2', lambda: call_lecture(title, summary, source, direction, cost_sink=cost_sink), results)
    results['histoire'] = _run_block(
        'B3', lambda: call_histoire(title, summary, source,
                                    guide=results['noyau']['guide'],
                                    concepts=results['noyau']['concepts'],
                                    cost_sink=cost_sink), results)

    # 4. Assemblage final (§3.1, provenance §4.6).
    return _assemble_lesson(lesson_meta, results)


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Glue génération↔persistance : helpers internes
# ───────────────────────────────────────────────────────────────────────────────
# Additif. Écritures DB COURTES et atomiques (la génération IA, lente et faillible,
# reste HORS transaction — décidé : pas de transaction ouverte pendant des appels
# réseau). Remap des clés générées (concepts→concepts_data, etc.) à la création de
# la version immuable. Ces helpers seront orchestrés par persist_generated_unit /
# resume_unit / regenerate_lesson (étapes suivantes).
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def _create_unit_skeleton(architect_structure: dict, *, teacher, school=None,
                          subject=None,
                          subject_type=SubjectType.OTHER,
                          level=EducationLevel.FONDAMENTAL_1, level_detail='',
                          source_file=None, source_type='pdf', language='fr',
                          initial_status=LessonStatus.PROCESSING) -> Unit:
    """Crée l'Unit + N Lesson shells depuis la structure Architecte, ATOMIQUEMENT
    (soit le squelette entier, soit rien).

    Les shells portent l'identité de chaque leçon (title/summary/slug=id) — tout ce
    qu'il faut pour régénérer en cas d'échec, sans re-stocker le JSON Architecte. Les
    métadonnées document-level (subject/direction/source) vivent sur l'Unit.

    subject : matière du document. Si fourni (vue d'upload : matière CHOISIE par le
    prof = vérité terrain), il FAIT FOI ; sinon on retombe sur la détection Architecte.
    Principe : l'IA détecte la STRUCTURE (titre/direction/leçons), le prof possède le
    CONTEXTE (matière/classe/niveau).

    initial_status : statut initial de l'Unit ET des shells. Défaut PROCESSING
    (persist_generated_unit, génération immédiate). La vue d'upload v2 passe DRAFT
    (« en attente » : confirmer-lite, la génération attend le bouton « Lancer »).
    DRAFT comme PROCESSING sont non-ready → resume_unit les traite comme « à générer ».
    Retourne l'Unit."""
    unit = Unit.objects.create(
        teacher=teacher, school=school,
        title=architect_structure['unit_title'],
        subject=subject if subject else architect_structure.get('subject', ''),
        subject_type=subject_type,
        level=level, level_detail=level_detail,
        language=language,
        direction=architect_structure.get('direction', 'ltr'),
        source_file=source_file, source_type=source_type,
        status=initial_status,
    )
    for idx, meta in enumerate(architect_structure['lessons']):
        Lesson.objects.create(
            teacher=teacher, school=school, unit=unit,
            title=meta['title'],
            summary=meta.get('summary', ''),
            slug=meta.get('id', ''),
            order=idx,   # séquence Architecte (réordonnable par le prof)
            # Les shells héritent l'identité matière de l'Unit (groupement du parcours
            # élève par matière). subject vivait seulement sur l'Unit → leçons à vide.
            subject=unit.subject,
            subject_type=unit.subject_type,
            level=unit.level,
            level_detail=unit.level_detail,
            format_version=2,
            status=initial_status,
        )
    return unit


@transaction.atomic
def _persist_lesson_version(lesson, generated: dict, lesson_cost) -> LessonContentVersion:
    """Write unifié v1 / v(N+1) : crée une LessonContentVersion IMMUABLE depuis l'objet
    généré (§3.1), avec REMAP des clés, pose le pointeur live et passe la leçon ready.

    Réutilisé en première création (count 0 → v1) ET en régénération (count N →
    v(N+1) + bascule du pointeur ; l'ancienne version + sa progression restent
    intactes). Retourne la version créée."""
    version = lesson.content_versions.count() + 1
    cv = LessonContentVersion.objects.create(
        lesson=lesson,
        version=version,
        concepts_data=generated['concepts'],   # remap concepts → concepts_data
        reading_data=generated['reading'],     # remap reading  → reading_data
        exam_data=generated['exam'],           # remap exam     → exam_data
        story_data=generated['story'],         # remap story    → story_data
        color=generated.get('color', ''),
        guide=generated.get('guide', ''),
        ai_provider_used=AIProvider.CLAUDE,
        generation_cost_usd=lesson_cost,
    )
    lesson.active_content_version = cv
    lesson.status = LessonStatus.READY
    lesson.save(update_fields=['active_content_version', 'status', 'updated_at'])
    return cv


@transaction.atomic
def _finalize_unit_status(unit) -> None:
    """Statut final de l'Unit selon ses leçons : toutes ready → READY ; ≥1 ready ET
    ≥1 non-ready → PARTIAL ; aucune ready → ERROR."""
    statuses = list(unit.lessons.values_list('status', flat=True))
    ready = sum(1 for s in statuses if s == LessonStatus.READY)
    total = len(statuses)
    if total and ready == total:
        unit.status = LessonStatus.READY
    elif ready:
        unit.status = LessonStatus.PARTIAL
    else:
        unit.status = LessonStatus.ERROR
    unit.save(update_fields=['status', 'updated_at'])


def _lesson_meta(lesson) -> dict:
    """Reconstruit le lesson_meta pour generate_lesson_v2 depuis le shell + l'Unit
    (subject/direction vivent au niveau document, sur l'Unit)."""
    unit = lesson.unit
    return {
        'id':        lesson.slug,
        'title':     lesson.title,
        'summary':   lesson.summary,
        'subject':   unit.subject if unit else None,
        'direction': unit.direction if unit else 'ltr',
    }


def _generate_pending_lessons(unit, source, on_lesson_done=None) -> Decimal:
    """Boucle de remplissage : génère + persiste les leçons NON-ready de l'unit.

    Idempotent : les leçons ready sont SAUTÉES (jamais régénérées). La génération
    (generate_lesson_v2) tourne HORS transaction ; seules les écritures sont en txn
    courte. Une leçon qui échoue (LessonBlockError) → ERROR, les autres CONTINUENT.

    on_lesson_done : callable optionnel appelé APRÈS chaque leçon (succès OU échec).
    Sert au heartbeat du verrou de génération (re-tampon après chaque leçon). Param
    optionnel, défaut None → comportement inchangé (comme cost_sink).
    Retourne le coût total (Decimal) des leçons RÉUSSIES, pour MAJ Unit.generation_cost_usd."""
    total_cost = Decimal('0')
    for shell in unit.lessons.exclude(status=LessonStatus.READY):
        lesson_costs = []  # cost_sink frais PAR leçon
        try:
            generated = generate_lesson_v2(_lesson_meta(shell), source, cost_sink=lesson_costs)
            lesson_cost = sum(lesson_costs)
            _persist_lesson_version(shell, generated, lesson_cost)  # txn courte → ready
            total_cost += lesson_cost
        except LessonBlockError:
            with transaction.atomic():
                shell.status = LessonStatus.ERROR
                shell.save(update_fields=['status', 'updated_at'])
        finally:
            if on_lesson_done is not None:
                on_lesson_done()  # heartbeat : re-tampon du verrou après chaque leçon
    return total_cost


def persist_generated_unit(architect_structure: dict, source, *, teacher, school=None,
                           subject_type=SubjectType.OTHER,
                           level=EducationLevel.FONDAMENTAL_1, level_detail='',
                           source_file=None, source_type='pdf', language='fr') -> Unit:
    """Création v2 complète : skeleton (Unit + shells) puis remplissage par génération.

    architect_structure : sortie de call_architect (DÉJÀ produite par l'appelant).
    source : le document ENTIER (str OU blocs image base64), passé à chaque leçon.
    Inputs teacher/serveur (subject_type/level/… sans source IA) en keyword-only.

    La génération (generate_lesson_v2) tourne HORS transaction (lente) ; seules les
    écritures (skeleton, version, marquage error, statut final) sont en txn courte
    (via les helpers). Une leçon qui échoue (LessonBlockError) est marquée ERROR
    SANS faire échouer les autres.

    Coût Architecte HORS scope ici (architect_structure est déjà produit) →
    Unit.generation_cost_usd = somme des coûts des LEÇONS réussies. On pourra
    ajouter le coût Architecte en paramètre plus tard si besoin.
    Retourne l'Unit rafraîchie."""
    unit = _create_unit_skeleton(
        architect_structure, teacher=teacher, school=school,
        subject_type=subject_type, level=level, level_detail=level_detail,
        source_file=source_file, source_type=source_type, language=language,
    )

    total_cost = _generate_pending_lessons(unit, source)
    _finalize_unit_status(unit)
    unit.generation_cost_usd = total_cost
    unit.save(update_fields=['generation_cost_usd', 'updated_at'])
    unit.refresh_from_db()
    return unit


def resume_unit(unit, source, on_lesson_done=None) -> Unit:
    """Reprise après échec partiel : ré-exécute la boucle de remplissage sur les leçons
    NON-ready de l'unit. Les leçons ready sont SAUTÉES (idempotence gratuite : pas de
    version parasite). Le coût des leçons régénérées s'AJOUTE à Unit.generation_cost_usd.
    on_lesson_done : callback optionnel (heartbeat) forwardé à _generate_pending_lessons.
    Retourne l'unit rafraîchie."""
    added_cost = _generate_pending_lessons(unit, source, on_lesson_done=on_lesson_done)
    _finalize_unit_status(unit)
    if added_cost:
        unit.generation_cost_usd = (unit.generation_cost_usd or Decimal('0')) + added_cost
        unit.save(update_fields=['generation_cost_usd', 'updated_at'])
    unit.refresh_from_db()
    return unit


def regenerate_lesson(lesson, source) -> LessonContentVersion:
    """Régénération volontaire d'une leçon DÉJÀ ready → nouvelle version v(N+1) +
    bascule du pointeur active_content_version. L'ancienne version ET sa progression
    (PROTECT) restent INTACTES.

    Sémantique différente de la reprise (qui remplit des leçons jamais réussies).
    NON destructif sur échec : la génération tourne AVANT toute écriture, donc si elle
    lève LessonBlockError, la leçon n'est PAS modifiée (l'ancienne version reste
    active) — une leçon qui marchait n'est jamais dégradée. L'exception se propage à
    l'appelant. Retourne la nouvelle version."""
    lesson_costs = []
    generated = generate_lesson_v2(_lesson_meta(lesson), source, cost_sink=lesson_costs)  # peut lever
    lesson_cost = sum(lesson_costs)
    cv = _persist_lesson_version(lesson, generated, lesson_cost)  # v(N+1) + bascule pointeur

    unit = lesson.unit
    if unit:
        if lesson_cost:
            unit.generation_cost_usd = (unit.generation_cost_usd or Decimal('0')) + lesson_cost
            unit.save(update_fields=['generation_cost_usd', 'updated_at'])
        _finalize_unit_status(unit)
    return cv


# ═══════════════════════════════════════════════════════════════════════════════
# v2 (PORTAL_V2_SPEC) — Lancement de la génération en tâche de fond (vue v2, couche 2)
# ───────────────────────────────────────────────────────────────────────────────
# Génération longue (~13 min/unité) → thread daemon (pattern v1, pas de Celery).
# Verrou anti-double-thread sur Unit.generation_lock_at : acquisition par UPDATE
# atomique conditionnel (anti-TOCTOU), expiration par heartbeat (re-tampon après
# chaque leçon) → robuste quelle que soit la taille de l'unité, et un thread mort
# ne bloque jamais à jamais. Verrou ≠ statut (cf. §7.1).
# ═══════════════════════════════════════════════════════════════════════════════

GENERATION_LOCK_TIMEOUT = timedelta(minutes=6)  # une leçon (~4 min) + marge ; heartbeat re-tamponne


def _acquire_generation_lock(unit) -> bool:
    """Acquiert le verrou de génération par UPDATE ATOMIQUE conditionnel (anti-TOCTOU).

    Pose generation_lock_at=now ssi le verrou est libre (null) OU PÉRIMÉ (< now - timeout).
    Retourne True si acquis, False si un verrou FRAIS existe (génération déjà en cours).
    Le rowcount de l'UPDATE garantit qu'un seul concurrent l'obtient (pas de check-then-set)."""
    stale_before = timezone.now() - GENERATION_LOCK_TIMEOUT
    acquired = (Unit.objects
                .filter(pk=unit.pk)
                .filter(Q(generation_lock_at__isnull=True) | Q(generation_lock_at__lt=stale_before))
                .update(generation_lock_at=timezone.now()))
    return acquired == 1


def _heartbeat_generation_lock(unit) -> None:
    """Re-tamponne le verrou (appelé après chaque leçon) → un job vivant reste verrouillé
    quelle que soit sa durée totale ; seul un thread mort laisse le verrou expirer."""
    Unit.objects.filter(pk=unit.pk).update(generation_lock_at=timezone.now())


def _release_generation_lock(unit) -> None:
    """Libère le verrou (fin du thread, succès ou échec). L'expiration reste le filet
    si le thread meurt sans passer ici."""
    Unit.objects.filter(pk=unit.pk).update(generation_lock_at=None)


def is_generation_active(unit) -> bool:
    """True si un thread de génération est (vraisemblablement) actif : verrou posé ET
    non périmé. Sert au suivi UI (afficher « en cours » vs le bouton Lancer/Reprendre)."""
    if unit.generation_lock_at is None:
        return False
    return unit.generation_lock_at >= timezone.now() - GENERATION_LOCK_TIMEOUT


def _generate_unit_worker(unit_id) -> None:
    """Corps du thread de fond : remplit les leçons non-ready d'une unité.

    Self-contained : re-extrait le contenu depuis unit.source_file (unifie 1ère
    génération et reprise). close_old_connections() pour une connexion DB propre dans
    le thread. Le verrou est TOUJOURS libéré (finally), même si la génération lève."""
    close_old_connections()
    unit = Unit.objects.get(pk=unit_id)
    try:
        content = extract_content_from_file(unit.source_file.path, unit.source_type)
        resume_unit(unit, content,
                    on_lesson_done=lambda: _heartbeat_generation_lock(unit))
    except Exception as e:
        logger.error('Génération unité %s échouée : %s', unit_id, e)
    finally:
        _release_generation_lock(unit)


def launch_unit_generation(unit) -> bool:
    """Lance la génération en fond pour une unité (1ère génération OU reprise).

    Acquiert le verrou (atomique) ; si un verrou frais existe → return False (déjà
    en cours, ne spawn pas). Sinon spawn un thread daemon et return True."""
    if not _acquire_generation_lock(unit):
        return False
    threading.Thread(target=_generate_unit_worker, args=[unit.id], daemon=True).start()
    return True
