# Catalogue des types de quiz — document fondateur

> **Pour la nouvelle plateforme d'apprentissage.** Ce document est le CONTRAT entre
> le cerveau IA (qui génère le contenu) et l'application (qui affiche, fait interagir
> et corrige). Issu d'une recherche sourcée (Brilliant, Khan Academy, Quizlet, Kahoot,
> DataCamp, standard QTI v3.0, littérature scientifique) — vote adversarial 3-0 sur
> chaque affirmation vérifiée.
>
> **Statuts** : ✅ vérifié (source primaire) · 🟡 usage établi (non vérifié en primaire) · ⚠️ à confirmer

---

## 1. La règle d'or — frontière IA ↔ App

Confirmée par le standard international **QTI v3.0** (format d'échange des questions
entre systèmes éducatifs) et par l'architecture de Khan Academy :

| 🧠 L'IA PRODUIT (données JSON) | 📱 L'APP GÈRE (jamais l'IA) |
|---|---|
| Énoncé | Rendu, affichage, thème |
| Options + **distracteurs plausibles** | Glisser-déposer, clavier, tap |
| Bonne réponse / solution cible | **Validation** (parsing, comparaison, tolérance) |
| Explication (montrée APRÈS la tentative) | Animation, son, vibration |
| Indices (gradués) | Minuteur |
| Difficulté, tags de concept | **Sélection adaptative** (quel item, quand) |
| Blocs Parsons + indentation attendue | SRS (intervalles de révision) |
| Média à produire (texte du TTS, description d'image) | Lecture audio, affichage média |

**En une phrase** : *l'IA écrit le contenu d'une question dans un schéma JSON figé ;
l'app sait afficher, faire interagir et corriger chaque type de schéma. Aucun appel
IA au moment où l'élève répond.*

Cas canonique (Khan, type « expression ») : le contenu fournit **seulement la solution
cible** ; l'app parse l'entrée de l'élève et la compare **sémantiquement** (x+1 ≡ 1+x),
avec feedback en direct. ✅

---

## 2. Schéma commun à TOUT item

Chaque question, quel que soit son type, porte ces champs communs :

```json
{
  "id": "q_...",
  "type": "<un des types du catalogue>",
  "instruction": "L'énoncé, clair et autoporteur.",
  "difficulty": 1,              // 1-3 (facile → difficile)
  "concept": "slug-du-concept", // rattachement pour SRS + progrès
  "explanation": "Montrée APRÈS la tentative — jamais avant (pretesting, Brilliant ✅).",
  "hints": ["indice léger", "indice plus direct"],   // optionnel, gradués
  "media": {                    // optionnel
    "audio_text": "Texte à lire par TTS (audio partout — accessibilité).",
    "image": "ref-ou-description"
  }
}
```

**Règles de génération pour l'IA** (Univ. Michigan, guides MCQ ✅) :
- Les **distracteurs** doivent être des **erreurs typiques plausibles**, pas des absurdités.
- L'**explication** explique *pourquoi* la bonne réponse est bonne **et** pourquoi le
  distracteur principal est tentant.
- Viser le **rappel** (production) plutôt que la simple reconnaissance quand c'est possible.
- Chaque item est **autoporteur** : compréhensible sans relire la leçon.

---

## Vue d'ensemble du catalogue

| Famille | Nombre | Détail |
|---|---|---|
| A. Universels | **13** | A1-A13 |
| B. Maths | **1** (+1 propriété) | expression sémantique ; paramétrage aléatoire = propriété transversale |
| C. Code | **4** | Parsons, code à trous, prédire la sortie, trouver le bug |
| D. Langues/audio | **3** (+1 parqué) | banque de mots, dictée, écouter-choisir ; prononciation = v2+ |
| **Types corrigés (jouables, avec score)** | **21** | |
| E. Formats d'engagement (sans score) | **3** | sondage, nuage de mots, question ouverte |
| **Total catalogue** | **24 entrées** | + 1 propriété + 1 parqué |

## 3. Catalogue — A. Types universels

### A1. QCM simple ✅ *(Khan « radio », Kahoot « quiz »)*
- **Mécanique** : une question, 3-5 options, une seule bonne.
- **IA produit** : `options[]`, `answer_index`, distracteurs plausibles.
- **App gère** : mélange des options, sélection, verrouillage, feedback.
- **Quand** : vérification rapide de compréhension. Le plus faible pédagogiquement
  s'il est seul (réussite possible par élimination ✅ Quizlet) — à mélanger avec des types de production.

### A2. QCM multiple ✅ *(Khan « multiple »)*
- **Mécanique** : cocher TOUTES les bonnes réponses.
- **IA produit** : `options[]`, `answer_indices[]`.
- **App gère** : états coché/oublié/à tort, validation ensembliste.
- **Quand** : notions à facettes multiples (« lesquels sont… »).

### A3. Vrai / Faux ✅ *(Kahoot)*
- **Mécanique** : une affirmation, deux boutons.
- **IA produit** : `statement`, `answer` (bool). L'affirmation doit être **franche**
  (pas de « parfois »).
- **Quand** : casser une idée reçue ; rythme rapide entre deux items lourds.

### A4. Saisie libre écrite ⭐ ✅ *(Quizlet « written » — LE plus efficace)*
- **Mécanique** : l'élève TAPE la réponse de mémoire, sans options.
- **IA produit** : `answers[]` (réponse canonique + variantes/synonymes acceptés).
- **App gère** : matching tolérant (casse, accents, espaces) — défini au runtime,
  **sans appel IA**. Question ouverte de recherche : jusqu'où pousser le flou (voir §7).
- **Pourquoi ⭐** : force le **rappel actif** — la stratégie n°1 de la science de
  l'apprentissage (testing effect, d≈0,56 ✅). Quizlet augmente sa fréquence à mesure
  que l'élève progresse (maîtrise adaptative ✅).

### A5. Réponse numérique ✅ *(Khan « decimal »)*
- **Mécanique** : taper un nombre.
- **IA produit** : `answer` (nombre), `tolerance`, `unit` (optionnel).
- **App gère** : clavier numérique, virgule/point, comparaison avec tolérance.
- **Quand** : calculs, estimations, données chiffrées.

### A6. Texte à trous (cloze) ✅
- **Mécanique** : phrase avec 1-3 blancs à compléter.
- **IA produit** : `text` avec marqueurs `{{0}}`, `{{1}}`… + `answers[]`.
- **App gère** : découpage, inputs inline, matching tolérant par blanc.
- **Quand** : vocabulaire, définitions, formules verbales.

### A7. Appariement (matching) ✅ *(Quizlet, Khan)*
- **Mécanique** : relier chaque élément de gauche à son partenaire de droite.
- **IA produit** : `pairs[] {left, right}` (3-6 paires).
- **App gère** : mélange de la colonne droite, liaison tap-tap ou drag, validation par paire.
- **Quand** : terme↔définition, cause↔effet, mot↔traduction.

### A8. Remise en ordre ✅ *(Kahoot « puzzle »)*
- **Mécanique** : remettre des éléments dans le bon ordre (chronologie, étapes, tailles).
- **IA produit** : `items[]` (dans le désordre) + `correct_order[]`.
- **App gère** : drag ou flèches ▲▼, validation position par position.
- **Quand** : processus, chronologies, procédures.

### A9. Classification ✅ *(DataCamp « classify », Khan « category »)*
- **Mécanique** : trier des cartes dans 2-3 paniers (ex. « recette / dépense »).
- **IA produit** : `buckets[]`, `cards[] {text, bucket_index}`.
- **App gère** : drag des cartes, validation par carte.
- **Quand** : catégoriser, distinguer des familles de concepts.

### A10. Curseur / slider ✅ *(Kahoot)*
- **Mécanique** : estimer une valeur en glissant un curseur sur une échelle.
- **IA produit** : `min`, `max`, `step`, `answer`, `tolerance`.
- **App gère** : le slider, la zone de tolérance, l'animation de révélation.
- **Quand** : ordres de grandeur, estimation, intuition numérique (esprit Brilliant).

### A11. Flashcard (auto-évaluation) ✅ *(Quizlet, Anki)*
- **Mécanique** : recto (question) → l'élève répond mentalement → révèle le verso →
  s'auto-évalue (« je savais / je ne savais pas »).
- **IA produit** : `front`, `back`.
- **App gère** : flip, boutons d'auto-évaluation, **branchement direct au SRS**.
- **Quand** : mémorisation pure (vocabulaire, dates, définitions). Le carburant
  naturel de la répétition espacée.

### A12. L'intrus (odd one out) 🟡 *(usage établi)*
- **Mécanique** : 4 éléments, un seul n'appartient PAS au groupe — le trouver.
- **IA produit** : `items[]`, `odd_index`, et la **règle du groupe** (pourquoi les
  trois autres vont ensemble — nourrit l'explication).
- **App gère** : sélection, feedback.
- **Quand** : discrimination fine entre concepts proches ; force à identifier le
  critère commun (plus exigeant qu'un QCM classique).

### A13. K-prime (série d'affirmations V/F) 🟡 *(format établi, évaluation médicale)*
- **Mécanique** : 3-4 affirmations sur UN même sujet ; chacune se juge Vrai/Faux
  indépendamment. Réussi si tout est correct.
- **IA produit** : `statements[] {text, answer}` — mélanger vraies et fausses.
- **App gère** : toggles V/F par ligne, validation d'ensemble, correction ligne à ligne.
- **Quand** : tester les nuances d'un concept (ce qui est vrai ET ce qui est faux) ;
  réduit fortement la réussite au hasard (1 chance sur 8-16 contre 1 sur 4 au QCM).

---

## 4. Catalogue — B. Types spécifiques par domaine

### Maths

### B1. Expression mathématique ✅ *(Khan « expression »)*
- **Mécanique** : l'élève saisit une expression (clavier math) ; comparaison **sémantique**
  (2x+1 ≡ 1+2x).
- **IA produit** : `solution` + contraintes optionnelles (`simplify`, `same_form`).
- **App gère** : l'éditeur math (MathQuill/MathLive), le parsing, la comparaison —
  100 % côté app, jamais la bonne réponse chez le client.
- **Quand** : algèbre, formules. Type le plus exigeant techniquement côté app.

### B2. Énoncé paramétré (variables aléatoires) ✅ *(principe khan-exercises)*
- **Ce n'est pas un type mais une PROPRIÉTÉ** applicable aux types numériques :
  l'énoncé contient des variables (`{a}`, `{b}`) tirées au sort à chaque affichage.
- **IA produit** : `variables {a: {min,max,step}}`, `formula_template` (« a + b »),
  `solution_formula`.
- **App gère** : le tirage, le calcul de la réponse attendue à partir de la formule.
- **Pourquoi** : l'élève ne peut pas mémoriser la réponse → refaisable à l'infini
  (pilier de l'apprentissage par maîtrise).

### Code

### B3. Puzzle Parsons ✅ *(DataCamp, arXiv 2311.18115 / 2401.12125)*
- **Mécanique** : lignes de code mélangées à remettre dans l'ordre **avec la bonne
  indentation**.
- **IA produit** : `lines[] {id, text}` + `sequence[] {text, indent}` (la solution).
- **App gère** : drag + boutons d'indentation, coloration syntaxique, validation
  ligne/indentation.
- **Pourquoi ✅** : échafaudage prouvé entre « lire des exemples » et « écrire seul » ;
  réduit la charge cognitive. Un LLM peut même en générer de **personnalisés à partir
  du code erroné de l'élève** (CodeTailor, ACM 2024 ✅) — piste v2 puissante.

### B4. Code à trous ✅ *(PFP, MDPI 2025 ; DataCamp)*
- **Mécanique** : code source avec des expressions masquées à compléter.
- **IA produit** : `code` avec `{{0}}`…, `answers[]`, `language`.
- **App gère** : rendu code + inputs inline, string matching (plancher — prévoir
  normalisation espaces/quotes).
- **Quand** : syntaxe, API, lecture de code.

### B5. Prédire la sortie 🟡 *(écoles de code — usage établi)*
- **Mécanique** : « Qu'affiche ce programme ? » → saisie libre ou QCM.
- **IA produit** : `code`, `language`, `answer` (la sortie exacte).
- **Quand** : compréhension de l'exécution, boucles, conditions.

### B6. Trouver le bug 🟡 *(usage établi)*
- **Mécanique** : code affiché ligne par ligne, tap sur la ligne fautive.
- **IA produit** : `code_lines[]`, `buggy_line` (index), `bug_explanation`.
- **Quand** : lecture critique, débogage.

### Langues / audio

### B7. Banque de mots ⚠️ *(Duolingo — non vérifié en source primaire)*
- **Mécanique** : construire la réponse en tapant des jetons dans l'ordre.
- **IA produit** : `tokens[]` (bons + intrus), `correct_sequence[]`.
- **App gère** : jetons tap-pour-placer, retrait, validation de séquence.
- **Quand** : construction de phrases, traduction, syntaxe.

### B8. Écouter → écrire (dictée) ⚠️ *(Duolingo)*
- **Mécanique** : audio joué → l'élève écrit ce qu'il entend.
- **IA produit** : `audio_text` (le TTS le lit), `answers[]`.
- **App gère** : lecteur audio (vitesse normale/lente), matching tolérant.
- **Quand** : compréhension orale — précieux en contexte de culture orale.

### B9. Écouter → choisir ⚠️ *(Duolingo)*
- **Mécanique** : audio joué → QCM.
- **IA produit** : `audio_text`, `options[]`, `answer_index`.
- **Quand** : discrimination auditive, vocabulaire oral.

### B10. Prononciation 🔴 *(Duolingo — HORS v1)*
- Reconnaissance vocale = technologie lourde, résultats inégaux. À réévaluer en v2+.

---

## 5. Catalogue — C. Formats SANS correction (engagement) ✅ *(Kahoot)*

Pas de bonne réponse — servent à animer, sonder, faire réfléchir :

- **C1. Sondage** : `options[]`, pas d'answer. Résultats agrégés affichés.
- **C2. Nuage de mots** : réponses libres courtes agrégées en nuage.
- **C3. Question ouverte / réflexion** : l'élève écrit ; pas de correction automatique
  (éventuelle relecture par le formateur).

À garder **hors du score** — leur rôle est l'engagement et la métacognition.

---

## 6. Les mécaniques d'apprentissage (la science, vérifiée)

1. **Testing effect / rappel actif** ✅ — se tester **fait apprendre** (d≈0,56 ;
   Roediger & Karpicke 2006, Schwieren 2017). Rappeler sans relire bat ré-étudier.
   → le quiz n'est pas une évaluation, c'est **l'apprentissage lui-même**.
2. **Feedback immédiat** ✅ — l'effet du test passe de g≈0,39 (sans feedback) à
   **g≈0,73 (avec)** (Rowland 2014). → correction + explication après CHAQUE question,
   jamais en fin de quiz seulement.
3. **Répétition espacée** ✅ — 2ᵉ stratégie la plus efficace (Dunlosky 2013).
   → un SRS (boîtes/intervalles croissants) branché sur les flashcards et les items ratés.
4. **Maîtrise adaptative** ✅ *(Quizlet Learn)* — commencer facile (QCM), et quand
   l'élève réussit, **augmenter la part des types difficiles** (saisie écrite).
   La sélection est du ressort de l'APP (statistiques), pas de l'IA.
5. **Pretesting / problème d'abord** ✅ *(Brilliant)* — laisser TENTER avant
   d'enseigner ; l'explication vient après la tentative. → dans une leçon, ouvrir
   par une question-défi avant le contenu.
6. **Leçon courte + gamification sobre** 🟡 — sessions de 3-8 min, série (streak),
   XP. Pour un public adulte : progression et satisfaction, sans infantilisation.
   (Sources blogs — principes plausibles, non vérifiés académiquement.)

---

## 7. Questions ouvertes (à trancher pendant la construction)

1. **Validation du texte libre** : où placer le curseur entre matching strict,
   normalisation (casse/accents), distance d'édition, synonymes pré-générés par l'IA ?
   Règle retenue : l'IA pré-génère les variantes acceptées ; l'app matche au runtime ;
   **jamais d'appel LLM à la soumission** (coût + latence).
2. **Schéma d'item unifié** : figer le JSON exact de chaque type (ce document en est
   la v0) et le versionner (`schema_version`) dès le premier jour.
3. **Génération des distracteurs** : imposer à l'IA de produire, pour chaque
   distracteur, l'**erreur typique** qu'il incarne (champ `distractor_rationale`) —
   améliore la qualité et nourrit les explications.
4. **Gamification adulte** : doser série/XP sans nuire à la motivation intrinsèque
   (risque documenté de « streak pour le streak »).

---

## 8. Couverture de la recherche (honnêteté)

- **Solide (sources primaires vérifiées)** : Brilliant (pédagogie), Khan (types de
  réponses, frontière données/moteur), Quizlet Learn (types + maîtrise adaptative),
  Kahoot (formats), DataCamp + arXiv/MDPI (code), science de l'apprentissage
  (testing effect, espacement, feedback), QTI v3.0 (architecture données/rendu),
  faisabilité IA (GPT-3 microlearning arXiv 2309.13060, CodeTailor).
- **Non vérifié en primaire** : détail exact des exercices Duolingo, algorithmes
  précis Anki/Memrise, Coursera/edX (peer review), Busuu/Babbel. → à documenter
  avant de finaliser les types B7-B10.
- **Réfuté** : Brilliant ne génère PAS ses interactifs par IA à la volée (0-3).
  → notre pipeline « document → leçon interactive par IA » est un différenciateur réel.

## Sources principales

- brilliant.org/about (pédagogie pretesting)
- github.com/Khan/khan-exercises — wiki « Answer Types »
- help.quizlet.com — « Studying with Learn »
- support.kahoot.com — « Kahoot question types »
- instructor-support.datacamp.com — « Exercise types »
- arXiv 2311.18115, 2401.12125 (Parsons, CodeTailor), 2309.13060 (micro-questions GPT-3)
- MDPI Information 2025 16(8) 709 (code fill-in-blank)
- Dunlosky et al. 2013 ; Roediger & Karpicke 2006 ; Schwieren et al. 2017 ; Rowland 2014
- 1EdTech QTI v3.0 Overview
