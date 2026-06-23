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
import time
import unicodedata
from decimal import Decimal
from pathlib import Path

import anthropic
import pdfplumber
import pypdfium2 as pdfium
from decouple import config

from .models import Lesson, LessonStatus, AIProvider

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
CLAUDE_MODEL      = 'claude-sonnet-4-6'
CLAUDE_MAX_TOKENS = 16_000

# Coût par million de tokens (USD) — ajuster si la grille tarifaire change.
CLAUDE_INPUT_COST_PER_M  = Decimal('3.00')
CLAUDE_OUTPUT_COST_PER_M = Decimal('15.00')

# Marqueur de la section "contenu" du prompt — réutilisé pour le mode images.
_CONTENT_SECTION = '\nCONTENU SOURCE À STRUCTURER\n"""\n{content}\n"""'

SYSTEM_PROMPT = """Tu es un concepteur pédagogique expert pour des élèves d'Afrique de l'Ouest (Mali).
Ta mission : transformer le contenu de cours fourni en une leçon interactive complète.

RÈGLE ABSOLUE DE FORMAT
- Tu réponds UNIQUEMENT avec un objet JSON valide.
- AUCUN texte avant, AUCUN texte après, AUCUN bloc markdown.
- Le premier caractère de ta réponse est { et le dernier est }.

RÈGLE DE FOND
- Tu ne RÉSUMES pas le cours : tu le STRUCTURES intégralement, sans perdre de notion.
- Tu reformules pour rendre clair, tu ajoutes des exemples concrets du quotidien malien
  (marché, mangues, francs CFA, transport, champs, famille), mais tu couvres TOUT le contenu.
- Langue de sortie : {language}.

CONTEXTE
- Matière : {subject} (type : {subject_type})
- Niveau : {level} — précision : {level_detail}
- Adapte la difficulté au niveau :
    prescolaire / fondamental_1 -> phrases très courtes, concret, difficulté 1-2
    fondamental_2              -> difficulté 2-3
    secondaire_gen / _pro      -> difficulté 3-4, vocabulaire technique
    superieur                  -> difficulté 4-5, rigueur et nuances

STRUCTURE JSON EXACTE À PRODUIRE
{
  "metadata": {
    "title": "...", "subject": "{subject}", "subject_type": "{subject_type}",
    "level": "{level}", "level_detail": "{level_detail}", "language": "{language}",
    "estimated_duration_minutes": 30
  },
  "structured_content": {
    "blocks": [
      {
        "id": "b1", "order": 1,
        "type": "definition|example|key_points|warning|summary|reflection|pause",
        "content": "texte clair et complet",
        "highlight": true,
        "concept_id": "concept_court_snake_case",
        "examples": ["exemple concret 1", "exemple concret 2"]
      }
    ]
  },
  "story": {
    "title": "Titre bref de la situation",
    "setting": "Lieu et contexte en 1 phrase",
    "characters": [
      {"name": "Aminata", "role": "élève curieuse", "side": "left"},
      {"name": "Moussa", "role": "vendeur malin", "side": "right"}
    ],
    "dialogue": [
      {"type": "speech", "speaker": "Aminata", "text": "réplique du personnage..."},
      {"type": "narration", "text": "description du contexte..."},
      {"type": "question", "marker": "Q1", "speaker": "Moussa", "text": "question posée par Moussa ?"}
    ],
    "questions": [
      {"marker": "Q1", "question": "Question pédagogique complète", "concept_ref": "concept_id", "expected": "réponse attendue en minuscules sans accents"}
    ]
  },
  "quiz": {
    "concepts": [
      {
        "id": "phrase_declarative",
        "name": "La phrase déclarative",
        "order": 1,
        "icon": "📝",
        "quiz_ids": ["q1", "q2", "q3"]
      }
    ],
    "quizzes": [
      {
        "id": "q1", "concept_id": "...", "subject_type": "{subject_type}",
        "type": "<un type autorisé pour ce subject_type>",
        "question": "...",
        "options": ["A", "B", "C", "D"],
        "answer": "...", "answer_index": 0,
        "explanation": "pourquoi cette réponse",
        "hint": "indice sans donner la réponse",
        "difficulty": 1, "points": 1,
        "image_url": null
      }
    ]
  },
  "flashcards": {
    "flashcards": [
      {"id": "f1", "concept_id": "...", "front": "question courte", "back": "réponse mémorisable", "tags": ["..."]}
    ]
  }
}

TYPES DE QUIZ AUTORISÉS + FORMATS

mcq (QCM) :
  question: "texte de la question"
  options: ["A", "B", "C", "D"]
  answer: "texte exact de la bonne option"
  answer_index: 0 (index dans options)

true_false (Vrai/Faux) :
  question: "affirmation à évaluer"
  options: ["Vrai", "Faux"]
  answer: "Vrai" ou "Faux"
  answer_index: 0 ou 1

fill_blank (Compléter) :
  question: "La photosynthèse produit du ___ et de l'eau." (utiliser ___ pour le blanc)
  options: []
  answer: "glucose" (réponse attendue exacte)
  answer_index: -1

number_input (Réponse numérique) :
  question: "Combien de côtés a un hexagone ?"
  options: []
  answer: "6" (nombre sous forme de string)
  answer_index: -1
  tolerance: 0 (tolérance optionnelle, ex: 0.5)

ordering (Remettre dans l'ordre) :
  question: "Remets les étapes dans l'ordre :"
  options: ["Étape B", "Étape C", "Étape A"] (mélangées aléatoirement)
  answer: "Étape A|||Étape B|||Étape C" (ordre correct séparé par |||)
  answer_index: -1

short_answer (Réponse courte) :
  question: "Qui a découvert la pénicilline ?"
  options: []
  answer: "fleming" (en minuscules, sans accents pour comparaison souple)
  answer_index: -1

TYPES AUTORISÉS PAR MATIÈRE :
math       : mcq, true_false, number_input, fill_blank, ordering
scientific : mcq, true_false, fill_blank, ordering, short_answer
literary   : mcq, true_false, short_answer, fill_blank, ordering
language   : mcq, fill_blank, true_false, short_answer
accounting : mcq, number_input, true_false, fill_blank
geography  : mcq, true_false, short_answer, ordering
other      : mcq, true_false, fill_blank, short_answer
code       : mcq, true_false, fill_blank

CONSIGNES MATHÉMATIQUES
Si subject_type = math :
- Écris TOUTES les formules en LaTeX.
- Inline : $x^2 + y^2 = z^2$
- Display : $$\\frac{a}{b} = c$$
- Fractions : $\\frac{3}{4}$  ·  Exposants : $x^2$, $x^{n+1}$  ·  Racines : $\\sqrt{x}$

EXIGENCES DE VOLUME
- structured_content.blocks : 5 à 12 blocs couvrant TOUT le cours.
- story : dialogue immersif type messagerie. Règles :
    * 2 à 4 personnages MALIENS (Aminata, Moussa, Fatoumata, Ibrahima, Boubacar, Mariam, Oumar, Kadiatou...), noms maliens UNIQUEMENT, chacun avec side "left" ou "right".
    * 8 à 15 entrées de dialogue (type speech/narration/question), locuteurs alternés naturellement.
    * 3 à 6 entrées type=question, chacune posée PAR un personnage (speaker), avec un marker unique (Q1, Q2...) repris à l'identique dans story.questions[].
    * narration (type=narration) = décor/atmosphère, sans speaker.
    * Situation de vie quotidienne malienne (marché de Bamako, famille, école, taxi, champs, boutique, mosquée...).
    * questions[].expected = réponse courte en minuscules sans accents.
- quiz.concepts : 4 à 8 concepts pédagogiques distincts. id = snake_case identique aux concept_id
  des quizzes, name = titre lisible en {language}, icon = emoji représentatif, order = 1..N,
  quiz_ids = liste exacte des "id" des quizzes appartenant à ce concept.
- quiz.quizzes : 15 à 30 questions, difficulté croissante, types variés selon la table ci-dessus.
- flashcards.flashcards : 6 à 15 cartes, une par concept clé (concept_id réutilisé du contenu).
- N'utilise QUE les 6 types ci-dessus (mcq, true_false, fill_blank, number_input, ordering, short_answer). Jamais matching, hotspot ni code_completion.
""" + _CONTENT_SECTION

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

def build_generation_prompt(metadata: dict) -> str:
    """
    Injecte les variables de la leçon dans le prompt système.
    str.replace() (et non str.format()) car le prompt contient des accolades JSON.
    {content} reste intact : il est rempli plus tard dans _call_claude.
    """
    return (
        SYSTEM_PROMPT
        .replace('{subject_type}', metadata.get('subject_type', 'other'))
        .replace('{subject}', metadata.get('subject', ''))
        .replace('{level_detail}', metadata.get('level_detail', ''))
        .replace('{level}', metadata.get('level', ''))
        .replace('{language}', metadata.get('language', 'fr'))
    )


# ─── 3. Génération avec IA ───────────────────────────────────────────────────

def generate_lesson_with_ai(lesson: Lesson, provider: str = 'claude') -> dict:
    """
    Génère le contenu structuré d'une leçon via l'API IA.
    Met à jour lesson.status / ai_provider_used / generation_cost_usd.
    Retourne le JSON parsé ou lève une exception (status -> ERROR).
    """
    lesson.status = LessonStatus.PROCESSING
    lesson.generation_attempts += 1
    lesson.save(update_fields=['status', 'generation_attempts'])

    metadata = {
        'subject': lesson.subject,
        'subject_type': lesson.subject_type,
        'level': lesson.level,
        'level_detail': lesson.level_detail,
        'language': lesson.language,
    }

    try:
        content = extract_content_from_file(lesson.source_file.path, lesson.source_type)
        result = _call_claude(content, metadata)

        # Mapping des 4 JSONField (clés alignées avec Lesson.quiz_count / flashcard_count).
        lesson.structured_content = result.get('structured_content')
        lesson.quiz_data         = result.get('quiz')
        lesson.story_data        = result.get('story')
        lesson.flashcards_data   = result.get('flashcards')
        lesson.generation_cost_usd = result.get('_cost_usd', Decimal('0'))
        lesson.status = LessonStatus.READY
        lesson.ai_provider_used = AIProvider.CLAUDE
        lesson.processing_error = ''
        lesson.save(update_fields=[
            'structured_content', 'quiz_data', 'story_data', 'flashcards_data',
            'status', 'ai_provider_used', 'processing_error', 'generation_cost_usd',
        ])

        logger.info(
            'Leçon %s générée (%d quiz, %d flashcards)',
            lesson.id, lesson.quiz_count, lesson.flashcard_count,
        )
        return result

    except Exception as e:
        logger.error('Génération leçon %s échouée: %s', lesson.id, e)
        lesson.status = LessonStatus.ERROR
        lesson.processing_error = str(e)
        lesson.save(update_fields=['status', 'processing_error'])
        raise


def _call_claude(content, metadata: dict) -> dict:
    """Appelle Claude. Single-pass : texte OU images selon le type de contenu."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = build_generation_prompt(metadata)

    if isinstance(content, str):
        # PDF texte natif / texte : le contenu est injecté dans le prompt.
        user_content = [{'type': 'text', 'text': system_prompt.replace('{content}', content)}]
    else:
        # Images (PDF scanné ou photo) : Claude lit directement les images.
        user_content = [
            {
                'type': 'image',
                'source': {'type': 'base64', 'media_type': img['media_type'], 'data': img['data']},
            }
            for img in content
        ]
        prompt_without_content = system_prompt.replace(
            _CONTENT_SECTION,
            '\nCONTENU SOURCE : lis les images fournies ci-dessus.',
        )
        user_content.append({'type': 'text', 'text': prompt_without_content})

    start = time.time()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        messages=[
            {'role': 'user', 'content': user_content},
        ],
    )
    elapsed = time.time() - start

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (
        Decimal(input_tokens) / 1_000_000 * CLAUDE_INPUT_COST_PER_M
        + Decimal(output_tokens) / 1_000_000 * CLAUDE_OUTPUT_COST_PER_M
    )
    logger.info(
        'Claude: %d in / %d out / $%.6f / %.1fs',
        input_tokens, output_tokens, cost, elapsed,
    )

    raw = response.content[0].text
    return _parse_and_validate(raw, cost)


def _parse_and_validate(raw: str, cost: Decimal) -> dict:
    """Parse le JSON Claude et valide les clés obligatoires. Lève ValueError si invalide."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Récupération 1 : json-repair corrige virgules manquantes et erreurs internes.
        try:
            from json_repair import repair_json
            data = json.loads(repair_json(raw))
        except Exception:
            # Récupération 2 : tronque après la dernière } (troncature en fin de réponse).
            try:
                last_brace = raw.rfind('}')
                data = json.loads(raw[:last_brace + 1])
            except Exception:
                raise ValueError(f'JSON invalide: {e}\nDébut de la réponse: {raw[:200]}')

    required = ['metadata', 'structured_content', 'quiz', 'flashcards']
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f'JSON incomplet, clés manquantes: {missing}')

    if 'quizzes' not in data.get('quiz', {}):
        raise ValueError("data['quiz']['quizzes'] manquant")
    if 'flashcards' not in data.get('flashcards', {}):
        raise ValueError("data['flashcards']['flashcards'] manquant")

    data['_cost_usd'] = cost
    return data


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


def evaluate_answer(quiz: dict, student_answer) -> bool:
    """Évalue la réponse de l'élève selon le type de quiz. Retourne True si correct."""
    qtype = quiz.get('type', 'mcq')
    correct_answer = quiz.get('answer', '')

    if qtype in ('mcq', 'true_false'):
        try:
            return int(student_answer) == quiz.get('answer_index', -1)
        except (TypeError, ValueError):
            return False

    if qtype in ('fill_blank', 'short_answer'):
        return normalize_text(str(student_answer)) == normalize_text(str(correct_answer))

    if qtype == 'number_input':
        try:
            student_val = float(str(student_answer).replace(',', '.'))
            correct_val = float(str(correct_answer).replace(',', '.'))
            tolerance = float(quiz.get('tolerance', 0) or 0)
            return abs(student_val - correct_val) <= tolerance
        except (TypeError, ValueError):
            return False

    if qtype == 'ordering':
        if not isinstance(student_answer, list):
            return False
        correct_order = [s.strip() for s in str(correct_answer).split('|||')]
        student_order = [str(s).strip() for s in student_answer]
        return student_order == correct_order

    return False


def calculate_lesson_mastery(student, lesson) -> int:
    """
    % de maîtrise d'une leçon = dernières tentatives correctes / total quiz.
    1 requête (PostgreSQL DISTINCT ON quiz_id). Retourne 0-100.
    """
    from apps.student_learning.models import QuizAttempt

    quiz_ids = [q['id'] for q in (lesson.quiz_data or {}).get('quizzes', [])]
    if not quiz_ids:
        return 0

    latest = (
        QuizAttempt.objects
        .filter(student=student, lesson=lesson, quiz_id__in=quiz_ids)
        .order_by('quiz_id', '-attempted_at')
        .distinct('quiz_id')
        .values_list('is_correct', flat=True)
    )
    correct = sum(1 for ok in latest if ok)
    return int(correct / len(quiz_ids) * 100)


# ─── Phase 8 — Répétition espacée SM-2 ───────────────────────────────────────

def sm2_update(repetitions: int, ease_factor, interval: int, quality: int):
    """
    Algorithme SM-2. quality : 1=très dur, 2=dur, 4=facile, 5=très facile.
    Retourne (repetitions, ease_factor[Decimal], interval_days).
    """
    ef = float(ease_factor)

    if quality >= 3:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        ef = ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        ef = max(1.3, ef)
        repetitions += 1
    else:
        repetitions = 0
        interval = 1

    return repetitions, Decimal(str(round(ef, 2))), interval


def get_due_flashcards(student, limit=20):
    """Flashcards dues aujourd'hui, les plus en retard d'abord."""
    from django.utils import timezone
    from apps.student_learning.models import Flashcard
    return list(
        Flashcard.objects
        .filter(student=student, next_review_date__lte=timezone.localdate())
        .select_related('lesson')
        .order_by('next_review_date')[:limit]
    )


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


def call_architect(content) -> dict:
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
- Champs : "formula_template" (l'équation, ex. "a*x + b = c") ; "variables" (un objet
  où chaque variable a { "min", "max", "step" }) ; "solution_formula" (la formule qui
  CALCULE la réponse à partir des variables) ; "expected_input" ("numeric") ;
  "correct_answer" (valeur témoin d'un tirage).
- Exemple :
  { "type": "dynamic_formula", "instruction": "Résous a·x + b = c pour x.",
    "formula_template": "a*x + b = c",
    "variables": { "a": {"min":2,"max":9,"step":1}, "b": {"min":1,"max":20,"step":1},
                   "c": {"min":21,"max":60,"step":1} },
    "solution_formula": "(c - b) / a", "expected_input": "numeric", "correct_answer": 4 }
- Piège : "solution_formula" DOIT être une vraie formule CALCULABLE à partir des
  variables (ex. "(c - b) / a"), jamais une constante. Choisis des "min"/"max"/"step"
  qui donnent un résultat propre. Le serveur recalcule la réponse par élève.

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


def call_noyau(lesson_title: str, lesson_summary: str, source) -> dict:
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


def call_lecture(lesson_title: str, lesson_summary: str, source, direction: str = 'ltr') -> dict:
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
                  guide: str, concepts) -> dict:
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


def generate_lesson_v2(lesson_meta: dict, source) -> dict:
    """Orchestre la génération complète d'UNE leçon v2 (§4.6).

    lesson_meta : la leçon issue de l'Architecte — { id, title, summary, subject,
                  direction } (subject/direction du niveau unité ; id/title/summary
                  de la leçon).
    source : la portion de document de la leçon (str OU list de blocs image base64).

    Retourne l'objet leçon final (§3.1). Lève LessonBlockError si un bloc échoue 2×
    (l'erreur porte le bloc fautif + les blocs déjà réussis dans .partial).
    NE TOUCHE PAS au pipeline v1 (generate_lesson_with_ai)."""
    title = lesson_meta['title']
    summary = lesson_meta['summary']
    direction = lesson_meta.get('direction', 'ltr')
    results = {}  # accumule les blocs réussis → jamais reperdus

    # 1. B1 d'abord (ses concepts alimentent B3).
    results['noyau'] = _run_block('B1', lambda: call_noyau(title, summary, source), results)

    # 2. B2 puis 3. B3 (séquentiel ; indépendants → parallélisables plus tard).
    results['lecture'] = _run_block(
        'B2', lambda: call_lecture(title, summary, source, direction), results)
    results['histoire'] = _run_block(
        'B3', lambda: call_histoire(title, summary, source,
                                    guide=results['noyau']['guide'],
                                    concepts=results['noyau']['concepts']), results)

    # 4. Assemblage final (§3.1, provenance §4.6).
    return _assemble_lesson(lesson_meta, results)
