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

### PHASE 3 — Interface upload prof ✅ Terminée
- [x] `teacher_required` déplacé dans `apps/core/mixins.py` (import mis à jour dans teachers/views.py, `wraps` retiré)
- [x] `apps/lessons/views.py` : `lesson_list`, `lesson_upload` (validation + génération thread daemon), `lesson_detail` (stats + aperçu quiz + classes déploiement), `lesson_status` (polling HTMX, HX-Refresh sur états terminaux), `lesson_retry`
- [x] `apps/lessons/urls.py` (namespace `lessons`) monté sur `/teacher/lessons/`
- [x] Templates : `list.html` (stats + cards + état vide), `upload.html` (form 2 sections + drag&drop Alpine), `detail.html` (3 états processing/ready/error), `partials/lesson_status_card.html` (polling 2s)
- [x] Sidebar « Mes leçons » (section teacher)
- [x] Génération en thread d'arrière-plan (pas de Celery) ; statut via **polling HTMX** (robuste gunicorn)
- [x] Tests : list/upload/detail (3 états)/status (HX) — tous OK ; `check` clean

### PHASE 4 — Portail élève dashboard ✅ Terminée
- [x] `apps/student_learning/urls.py` (`app_name='learn'`) monté `/learn/`
- [x] Login élève `access_code` + nom (`authenticate_student` → `login_student`), session isolée `student_id`, redirection sûre `next`
- [x] `learn_dashboard` : matières distinctes (déploiements classe), switcher, nodes hexagonaux (états not_started/in_progress/completed + % blocs lus), leçon en cours, streak quotidien (`_update_streak`)
- [x] Stubs `lesson/quiz/flashcards/profile` (phases 5-9)
- [x] `base_student.html` (standalone, `output.css` + `student.css`, header XP/streak, bottom nav 4 items) + `login.html` + `dashboard.html` + `stub.html`
- [x] `static/css/student.css` : hexagones `clip-path`, rangées décalées, gradients par état, `scrollbar-hide`
- [x] `request.student` isolé de `request.user` (reste AnonymousUser, aucun crash SchoolMiddleware) — vérifié
- [x] Abonnement **non utilisé** (tout gratuit, décision actée)
- [x] Tests : login (bon/mauvais/vide), session, dashboard (états vide + nodes réels), switch matière, stub, logout — tous OK

### PHASE 5 — Lecture leçon ✅ Terminée
- [x] `{% block extra_head %}` ajouté à `base_student.html`
- [x] `SYSTEM_PROMPT` (services.py) : consignes LaTeX `$…$`/`$$…$$` pour subject_type=math
- [x] `learn_lesson` (remplace le stub) : `get_or_create` progress, blocs + note par bloc, KaTeX si math, teaser story, CTA quiz
- [x] `lesson_save_progress` (204, IntersectionObserver), `lesson_save_note` (notes reflection), `lesson_complete` (+20 XP inline, redirect dashboard)
- [x] `lesson.html` : 7 designs de blocs (definition/example/key_points/warning/summary/reflection/pause), IntersectionObserver + reprise scroll, barre de progression, KaTeX, bouton Terminer, teaser story 🎭, bottom nav masquée
- [x] Toast « +20 XP » via session (popé sur le dashboard, cible du redirect)
- [x] Navigation : scroll naturel ; Story différée Phase 10 ; XP inline (→ `award_xp()` Phase 9)
- [x] Tests client (read/progress/note/complete/XP/toast) + **vérif navigateur réel** (7 blocs rendus, KaTeX `\frac` OK) — tous verts

### PHASE 6 — Quiz engine ✅ Terminée
- [x] `SYSTEM_PROMPT` : formats par type (6 types, **matching/hotspot/code_completion retirés**) + types par matière
- [x] `services.py` : `normalize_text` (accents), `evaluate_answer` (6 types), `calculate_lesson_mastery` (1 requête DISTINCT ON)
- [x] `LessonProgress.quiz_bonus_awarded` (idempotence bonus) + migration `0002`
- [x] Vues `learn_quiz` (réponses **stripées** côté client via `json_script`), `quiz_submit` (eval serveur, +5 1re bonne réponse, `correct_index` renvoyé), `quiz_results` (score, bonus +30 idempotent)
- [x] `quiz.html` : question par question (Alpine), 6 types de saisie, SortableJS si ordering, KaTeX si math, feedback immédiat, coloration via `correct_index` serveur
- [x] `quiz_results.html` : score SVG circulaire, stats, bonus, maîtrise
- [x] Dashboard : node `done` si lu complété **OU** mastery ≥ 80% (décision c)
- [x] Décisions : question par question + feedback immédiat serveur (a) · +5 anti-farming (b) · 6 types sans matching (d)
- [x] Tests : 6 evaluateurs · anti-leak réponses · anti-farming · bonus idempotent · mastery node — tous verts

### PHASE 7 — Nodes hexagonaux « Ruche Vivante » ✅ Terminée
- [x] Glassmorphism : `backdrop-filter: blur`, bordure lumineuse (hex teinté ::before + verre inset), glow hexagonal via `filter: drop-shadow` (suit la forme, contrairement à box-shadow clippé)
- [x] Pulse continu sur node actif (`hexPulse` drop-shadow) + particules ⭐✨ flottantes pur CSS (`floatParticle`)
- [x] Badge numéro `01/02/03` (mono) + % maîtrise sous chaque node
- [x] Connecteurs verticaux colorés par état (vert lumineux / orange pointillé animé / gris)
- [x] Tooltip slide-from-bottom (Alpine `openNode`, 1 state partagé, data-* attributes) : badge matière, statut, barre maîtrise, bouton Commencer/Continuer contextuel
- [x] Fond animé `gradientShift` (background-image sur body, n'écrase pas la couleur Tailwind)
- [x] Confettis Canvas pur JS (`launchConfetti`) déclenchés à l'arrivée après complétion (`learn_toast`)
- [x] `[x-cloak]` ajouté à student.css (absent de base_student) — anti-flash du panel
- [x] Progressive enhancement : nodes = `<a href>` (fallback natif) + `@click.prevent` (panel une fois Alpine hydraté) ; fix CSS `display:block` (un `<a>` ignore width/height sinon) ; fix commentaire `{# #}` mono-ligne
- [x] Accès libre (pas de lock, décision a) · trait CSS (b) · tap (c) · pas de pagination (d)
- [x] Vue inchangée (mastery déjà fourni Phase 6) ; `check` OK ; **vérifié navigateur** (glow, pulse, particules, connecteurs, panel)

### PHASE 8 — Flashcards SM-2 ✅ Terminée
- [x] `services.py` : `sm2_update` (quadratique, clamp 1.3, Decimal) + `get_due_flashcards`
- [x] Création **Option B** : bulk `get_or_create` à la complétion de la leçon (idempotent via unique_together)
- [x] Vues `learn_flashcards` (paquets dues/total, 3 requêtes), `flashcards_session`, `flashcard_review` (POST SM-2)
- [x] Templates `flashcards.html` (paquets + barre), `flashcards_session.html` (flip card 3D + 4 boutons qualité)
- [x] Mapping qualité 😰1 / 😐2 / 🙂4 / 😄5 (reset sur 1-2) ; carte ratée repasse en fin de file (max 3/session)
- [x] Context processor `student_due_flashcards` (gate session, 1 COUNT) + badge rouge bottom nav
- [x] **Flip card via classes CSS `.flip-card-*`** (pas de `:style` inline qui clobbe `transform-style` → texte miroir) ; `widthratio` corrigé (`reviewed` calculé en vue)
- [x] Tests client (SM-2, Option B idempotent, session, review, badge) + **vérif navigateur** (flip recto/verso droit, boutons qualité) — tous verts

### PHASE 9 — Gamification XP/Badges ✅ Terminée
- [x] `apps/student_learning/services.py` : `award_xp` (recalcule niveau + badges), `check_badges` (13 badges), `student_stats`, `LEVEL_NAMES` 6 niveaux, helpers
- [x] **Refactor des 3 sites XP inline** (lesson_complete/quiz_submit/quiz_results) → `award_xp` — **corrige le bug** : quiz ne recalculait pas le niveau (`F('total_xp')` sans level)
- [x] Nouveaux gains : flashcard +2 (1re fois du cycle dû, anti-farming via `was_due`), streak 7→+100 / 30→+500 (idempotent)
- [x] Page profil `/learn/profile/` : avatar, badge niveau, barre XP, streak, 4 stats, grille badges (gagné coloré / verrou grisé) ; filtre `dict_key`
- [x] Toast + confettis montée de niveau ; `launchConfetti` **déplacé dans base_student.html** (partagé dashboard + quiz) ; overlay level-up quiz
- [x] Décisions : niveaux Novice→Génie (a) · 50 flashcards = somme révisions (b) · +2 1re fois cycle (c) · toast+confettis (d) · services student_learning (e)
- [x] Tests client (award/level-up/badges/anti-farming/streak/profil) + **vérif navigateur** (profil complet) — tous verts

### PHASE 10 — Stories interactives ✅ Terminée
- [x] `SYSTEM_PROMPT` story → **format dialogue** (Option B) : `title/setting/characters[side]/dialogue[{type:speech|narration|question}]/questions[{marker,expected}]` + règles (2-4 persos maliens, 8-15 échanges, 3-6 questions)
- [x] Vues `learn_story` (build dialogue **sans `expected`** anti-triche, couleurs persos), `story_answer` (éval serveur `normalize_text` + tolérance inclusion), `story_finish` (StoryAttempt + XP +25/≥50% ou +40/100%, **1re complétion** anti-farming)
- [x] `story.html` : bulles WhatsApp gauche/droite par personnage, avatars colorés, narration centrée, bulle question violette, input réponse, feedback vert/orange, écran final + confettis si 100%, révélation animée fadeSlideIn
- [x] Teaser `lesson.html` activé → `learn:story` (Nouveau/Rejouable selon `already_done`)
- [x] Décisions : dialogue (a) · XP +25/+40 1re fois (b) · `expected` free-text + tolérance inclusion (c)
- [x] Tests client (anti-leak expected, tolérance, anti-farming, teaser) + **vérif navigateur** (bulles dialogue) — tous verts

### Phases suivantes (à venir)
11. Répétition espacée · 12. Abonnements
