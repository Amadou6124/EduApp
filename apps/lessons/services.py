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
    "narrative": "Récit immersif avec marqueurs [Q1] [Q2] [Q3] où s'insèrent les questions.",
    "characters": [
      {"name": "Aminata", "role": "..."},
      {"name": "Moussa", "role": "..."}
    ],
    "questions": [
      {"after_marker": "Q1", "question": "...", "concept_ref": "concept_id", "expected": "..."}
    ]
  },
  "quiz": {
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
- story : 3 à 5 personnages MALIENS (Aminata, Moussa, Fatoumata, Ibrahima, Boubacar,
  Mariam, Oumar, Kadiatou...), 3 à 6 questions intercalées.
- quiz.quizzes : 8 à 20 questions, difficulté croissante, types variés selon la table ci-dessus.
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
            {'role': 'assistant', 'content': '{'},   # prefill -> force le JSON pur
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

    raw = '{' + response.content[0].text   # le prefill { n'est pas répété par l'API
    return _parse_and_validate(raw, cost)


def _parse_and_validate(raw: str, cost: Decimal) -> dict:
    """Parse le JSON Claude et valide les clés obligatoires. Lève ValueError si invalide."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Récupération : tronque après la dernière } si du texte parasite a été ajouté.
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
