# Portail Élève — EduApp

## Vision
Révolutionner l'apprentissage scolaire en Afrique. Dépasser Duolingo côté élèves.
Éliminer les cours de soutien inutiles. Permettre à chaque élève malien d'apprendre
depuis son téléphone, partout, à tout moment.

## Modèle économique
- Primaire : 10 000 FCFA/an
- Secondaire : 15 000 FCFA/an
- Université/Prépa : 25 000 FCFA/an
- 2ème enfant : -30% / 3ème+ : -50%
- Paiement annuel uniquement (rentrée)
- Gratuit : 3 leçons preview par matière
- IA : Claude Sonnet 4.6 (principal) / Gemini Flash (fallback)

## Architecture technique décidée
- Stack : Django + Alpine.js (pas React)
- IA : Claude API une seule passe
- Stockage : Cloudinary (prod) / local (dev)
- Async : SSE streaming puis django-q2
- Répétition espacée : algorithme SM-2
- Nodes : hexagonaux CSS clip-path
- Maths : KaTeX CDN
- Drag&drop : SortableJS CDN
- Code : CodeMirror 5 CDN (V2)

## Nouveaux modèles Django nécessaires

### apps/lessons/ (nouvelle app)

**Lesson**
- teacher = FK → User
- school = FK → School (nullable)
- title = CharField(200)
- subject = CharField(50)
- subject_type = CharField(20)  # literary/scientific/math/language/code/accounting/geography
- level = CharField(20)  # primaire_1_3/primaire_4_6/secondaire_1_3/secondaire_4/lycee/superieur
- language = CharField(5) default='fr'
- source_file = FileField (PDF/image)
- source_type = CharField(10)  # pdf/image/text
- structured_content = JSONField(null)  # blocs leçon structurée
- quiz_data = JSONField(null)  # tous les quiz générés
- story_data = JSONField(null)  # session de compréhension
- flashcards_data = JSONField(null)  # flashcards pour répétition espacée
- status = CharField(20)  # draft/processing/ready/error
- processing_error = TextField(blank)
- ai_provider_used = CharField(20)  # claude/gemini
- generation_cost_usd = DecimalField(8,6)
- is_public = BooleanField(default=False)  # partageable bibliothèque
- view_count = PositiveIntegerField(0)
- created_at = DateTimeField(auto_now_add)
- updated_at = DateTimeField(auto_now)

**LessonDeployment** — une leçon déployée dans une classe
- lesson = FK → Lesson
- school = FK → School
- school_class = FK → SchoolClass (nullable)
- deployed_by = FK → User
- deployed_at = DateTimeField(auto_now_add)
- is_active = BooleanField(default=True)
- Meta: unique_together = (lesson, school_class)

### apps/student_learning/ (nouvelle app)

**StudentSubscription**
- student = FK → User (role=student)
- level_type = CharField(20)  # primaire/secondaire/superieur
- subscription_type = CharField(20)  # free/premium/prepa
- price_paid = DecimalField(10,0)  # FCFA
- start_date = DateField
- end_date = DateField
- payment_method = CharField(20)  # orange_money/moov/wave/cash
- payment_reference = CharField(100, blank)
- is_active = BooleanField(default=True)
- created_by = FK → User (admin qui active)

**LessonProgress**
- student = FK → User
- lesson = FK → Lesson
- started_at = DateTimeField(auto_now_add)
- completed_at = DateTimeField(null)
- last_block_index = PositiveIntegerField(0)  # dernier bloc lu
- reading_time_seconds = PositiveIntegerField(0)
- is_completed = BooleanField(default=False)
- notes = JSONField(default=list)  # [{block_id, text, created_at}]
- Meta: unique_together = (student, lesson)

**QuizAttempt**
- student = FK → User
- lesson = FK → Lesson
- quiz_id = CharField(20)  # id du quiz dans quiz_data JSON
- question_type = CharField(30)
- student_answer = JSONField
- is_correct = BooleanField
- time_spent_seconds = PositiveSmallIntegerField
- attempted_at = DateTimeField(auto_now_add)
- Meta: indexes = [(student, lesson), (student, is_correct)]

**StoryAttempt**
- student = FK → User
- lesson = FK → Lesson
- score = PositiveSmallIntegerField  # % de bonnes réponses
- completed_at = DateTimeField(auto_now_add)
- answers = JSONField(default=list)

**Flashcard** (SM-2)
- student = FK → User
- lesson = FK → Lesson
- flashcard_id = CharField(20)  # id dans flashcards_data JSON
- ease_factor = DecimalField(4,2, default=2.50)
- interval_days = PositiveSmallIntegerField(1)
- repetitions = PositiveSmallIntegerField(0)
- next_review_date = DateField(auto_now_add)
- last_quality = PositiveSmallIntegerField(null)  # 0-5
- total_reviews = PositiveIntegerField(0)
- Meta: unique_together = (student, lesson, flashcard_id) ; indexes = [(student, next_review_date)]

**StudentXP**
- student = OneToOneField → User
- total_xp = PositiveIntegerField(0)
- current_level = PositiveSmallIntegerField(1)
- streak_days = PositiveSmallIntegerField(0)
- last_activity_date = DateField(null)
- longest_streak = PositiveSmallIntegerField(0)
- badges = JSONField(default=list)  # [{id, name, earned_at}]

XP PAR ACTION :
- Leçon lue complète = 20 XP
- Quiz correct = 5 XP
- Quiz parfait (100%) = 30 XP
- Node maîtrisé = 50 XP
- Story complétée = 25 XP
- Flashcard révisée = 2 XP
- Streak 7 jours = 100 XP bonus
- Streak 30 jours = 500 XP bonus

**DailyChallenge**
- student = FK → User
- date = DateField
- lesson = FK → Lesson (nullable)
- challenge_type = CharField(20)  # quiz_daily/flashcard_review/lesson_read/story_complete
- is_completed = BooleanField(default=False)
- completed_at = DateTimeField(null)
- xp_earned = PositiveSmallIntegerField(0)
- Meta: unique_together = (student, date)

### apps/lessons/services.py — fonctions à créer
1. extract_content_from_file(file_path, file_type) → str
2. generate_lesson_with_ai(content, metadata, provider='claude') → dict
3. sm2_update(repetitions, ease_factor, interval, quality) → (repetitions, ease_factor, interval)
4. get_due_flashcards(student, limit=20) → QuerySet Flashcard
5. calculate_lesson_mastery(student, lesson) → int (0-100 %)
6. update_streak(student_xp) → None
7. award_xp(student, xp_amount, reason) → None
8. get_or_create_daily_challenge(student) → DailyChallenge

### Nouveau profil élève (apps/accounts/) — à décider
Option retenue : **StudentProfile (OneToOne User)** plutôt que champs sur User
- student = OneToOneField → User
- school = FK → School
- school_class = FK → SchoolClass
- date_of_birth = DateField(null)
- parent = FK → User (role=parent, null)  # lien vers le compte parent existant
- enrollment_number = CharField(50, blank)

## Plan d'implémentation (12 phases)
1. Fondation modèles
2. Service IA (génération)
3. Interface upload prof
4. Portail élève dashboard
5. Interface leçon (lecture)
6. Quiz engine
7. Nodes hexagonaux
8. Flashcards + SM-2
9. Gamification XP/badges
10. Stories interactives
11. Répétition espacée (rappels + planning exam)
12. Abonnements + paiement

## Décisions actées (Phase 0)
1. **Identité élève → Option B** : l'élève reste un `students.Student` (pas un User). Login via `access_code` + nom de famille, session isolée (`request.student`, jamais `request.user`). Backend dédié `apps/core/student_auth.py`.
2. **Niveaux → `EducationLevel` malien réutilisé** (`Lesson.level`) + `level_detail` libre pour l'année exacte.
3. **Abonnement → système séparé** (`student_learning.StudentSubscription`), activation manuelle admin, API Orange Money en V2.
4. **Pas de `StudentProfile`** : champs auth + gamification ajoutés directement sur `Student`.

## Phases
### PHASE 1 — Fondation modèles ✅ Terminée
- [x] `students.Student` enrichi : `password`, `last_login` + gamification (`total_xp`, `current_level`, `streak_days`, `last_activity_date`, `longest_streak`, `badges`) + `set_student_password` / `check_student_password`
- [x] `apps/core/student_auth.py` : `authenticate_student` (désambiguïse par nom — codes uniques par école seulement), `_name_matches` (tolère nom malien en premier/dernier), `login_student` / `logout_student` (session isolée), `student_required`
- [x] `apps/lessons/` : `Lesson` (source + 4 JSONField IA + statut + coût) , `LessonDeployment` ; enums `SubjectType` / `LessonStatus` / `AIProvider`
- [x] `apps/student_learning/` : `StudentSubscription` (prix FCFA + `is_valid`), `LessonProgress`, `QuizAttempt`, `StoryAttempt`, `Flashcard` (SM-2), `DailyChallenge`
- [x] Migrations : `students/0005`, `lessons/0001`, `student_learning/0001` appliquées, `check` OK
- [x] Fix : `Flashcard.next_review_date` → `default=timezone.localdate` (date, pas datetime)

### PHASE 2 — Service IA (génération) ✅ Terminée
- [x] `apps/lessons/services.py`
- [x] `extract_content_from_file` : pdfplumber (PDF texte) → pypdfium2 rendu images (PDF scanné) → base64 (photo)
- [x] `build_generation_prompt` : assemblage par `str.replace` (prompt plein d'accolades JSON → `.format` impossible)
- [x] `generate_lesson_with_ai` : Claude single-pass (texte OU images), prefill `{`, mapping 4 JSONField, coût USD persisté, statut PROCESSING→READY/ERROR
- [x] `_parse_and_validate` : parse + validation clés obligatoires (`quiz.quizzes`, `flashcards.flashcards`)
- [x] `validate_lesson_file` : magic bytes (PDF/JPG/PNG) + max 10 Mo
- [x] `SYSTEM_PROMPT` (single-pass, personnages maliens, types quiz par subject_type, garde `code_completion`) + `EXTRACTION_PROMPT` (option future)
- [x] `ANTHROPIC_API_KEY` via `decouple.config()` (.env, gitignored) ; modèle `claude-sonnet-4-6`, `max_tokens=16000`
- [ ] Fallback Gemini : préparé (param `provider`), implémentation V2

### Phases suivantes (à venir)
3. Upload prof · 4. Dashboard élève · 5. Lecture leçon · 6. Quiz engine
7. Nodes hexagonaux · 8. Flashcards SM-2 · 9. Gamification · 10. Stories · 11. Répétition espacée · 12. Abonnements
