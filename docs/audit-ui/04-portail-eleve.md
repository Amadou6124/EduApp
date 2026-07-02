# Audit UI/UX — Portail Élève (apprentissage gamifié)

> **Audit en LECTURE SEULE.** Aucun fichier modifié. Portail en **état hybride V1/V2** :
> refonte V2 « niveau Duolingo » très avancée mais inachevée, V1 partiellement
> supprimé. Ce document distingue honnêtement ce qui est **terminé / en cours /
> abandonné**, preuves à l'appui (fichier:ligne).
>
> Périmètre : `templates/learn/{base_student,grades,profile,login}.html`,
> `templates/student_learning/*_v2.html` + `_rcheck.html`, `static/css/student.css`.
> Références croisées : `apps/student_learning/{views,urls}.py`, `PORTAIL_ELEVE.md`, `PORTAL_V2_SPEC.md`.

---

## 0. Synthèse — l'état réel de la refonte

Le portail élève est le **chantier le plus divergent** de l'app. Trois faits structurants :

1. **Le V1 a été délibérément supprimé** — commit `a132915` « suppression complète
   du portail v1 (UI, routes, vues, templates, services) » a effacé
   `dashboard.html`, `lesson.html`, `quiz.html`, `quiz_results.html`,
   `flashcards.html`, `flashcards_session.html`, `story.html` ; commit `07391cd`
   a retiré `stub.html`. Il ne **reste que 4 fichiers V1** : `base_student.html`,
   `login.html`, `profile.html`, `grades.html`.

2. **Le V2 est un système autonome, sophistiqué, presque complet** : 6 écrans
   `*_v2.html` (parcours, lecteur, quiz runner 13 types, exam runner, story, vide),
   chacun **standalone** (n'étend AUCUNE base), avec son **propre thème sombre
   inline**, ses propres state machines Alpine. C'est une **réécriture from scratch
   d'après une maquette React** (cf. `PORTAL_V2_SPEC.md §1.6`).

3. **Deux design systems coexistent dans le même portail** : V1 = Tailwind clair
   émeraude (`student-500`), Manrope via Google Fonts, `output.css` + `student.css` ;
   V2 = thème sombre violet (`#0b0b1a` / `#818CF8`), Manrope **vendored**, **zéro
   Tailwind**, CSS inline. Un élève qui navigue Parcours (sombre) → Profil (clair)
   change littéralement d'application.

**% de refonte terminé (estimation) : ~80 %.** Les 6 écrans cœur existent et sont
câblés à des vues réelles de production. Restent : 5 stubs `bientôt`, l'exam runner
qui ne couvre que **5 types sur 13**, les onglets nav Pratique/Révision vides, et
les 2 écrans V1 survivants (profil/notes) jamais reskinés en thème V2.

---

## 1. Carte V1 vs V2 — par écran

| Écran | Génération | Fichier | Étend base ? | État | Preuve |
|---|---|---|---|---|---|
| **Login** | V1 | `learn/login.html` | Non (standalone, propre `<html>`) | ✅ Terminé | Tailwind clair, dégradé émeraude `login.html:9`, `student-500` |
| **Base élève** | V1 | `learn/base_student.html` | — (c'est LA base) | ⚠️ Survivant / quasi-orphelin | N'est étendue **que** par profile + grades (`grep extends` → 2 hits) |
| **Profil** | V1 | `learn/profile.html` | **Oui** `base_student.html:1` | ⚠️ Terminé mais V1 (non reskiné V2) | `{% extends 'learn/base_student.html' %}`, colors `student-*`/`gold-*` |
| **Notes & Rangs** | V1 | `learn/grades.html` | **Oui** `base_student.html:1` | ⚠️ Terminé mais V1 (non reskiné V2) | `{% extends %}`, thème clair, bottom-nav V1 |
| **Dashboard V1 (zigzag)** | V1 | *(supprimé)* | — | ❌ **Abandonné/supprimé** | `dashboard.html` effacé (commit `a132915`) ; vue redirige vers V2 `views.py:102-104` |
| **Leçon V1 / Quiz V1 / Flashcards / Story V1** | V1 | *(supprimés)* | — | ❌ **Abandonnés/supprimés** | 7 templates effacés `a132915` ; routes retirées `urls.py:11` |
| **Écran vide** | V2 | `student_learning/empty_v2.html` | Non (standalone) | ✅ Terminé | Thème sombre inline, rendu par `views.py:104` |
| **Parcours (carte/chemin)** | V2 | `parcours_v2.html` | Non (standalone) | ✅ Terminé (cœur) — 1 CTA stub | Vue réelle `views.py:460-507` ; stub header `:138` |
| **Lecteur (Lire)** | V2 | `lecteur_v2.html` | Non (standalone) | 🟡 En cours — CTA exercices stub | Vue `views.py:527-564` ; `bientôt` `:165` |
| **Quiz Runner (13 types)** | V2 | `quiz_runner_v2.html` | Non (standalone) | ✅ Terminé | 13/13 types implémentés ; vue `views.py:950` |
| **Exam Runner** | V2 | `exam_runner_v2.html` | Non (standalone) | 🟡 En cours — 5/13 types | Vue `views.py:677` ; types mcq_single/multiple/tf/cloze/matching seulement |
| **Story (dialogue)** | V2 | `story_v2.html` | Non (standalone) | ✅ Terminé | 6 step types ; vue `views.py:586-601` + finish `:614` |
| **`_rcheck.html`** | V2 (partial) | `student_learning/_rcheck.html` | Inclus par lecteur | ✅ Terminé | `{% include %}` `lecteur_v2.html:153-154` |
| **Onglets Pratique / Révision** | V2 | (dans parcours nav) | — | ❌ Non implémentés | placeholder `parcours_v2.html:241-247`, `:328` |

**Bilan :** V1 = 4 fichiers (1 base + 1 login + 2 écrans non migrés). V2 = 7 fichiers
réels + 1 partial. V1 fonctionnel restant = **profil & notes uniquement**.

---

## 2. Arborescence — héritage vs autonomie

### Ce qui étend `base_student.html`
```
learn/base_student.html  (V1 base)
 ├── learn/profile.html   {% extends %}  (profile.html:1)
 └── learn/grades.html    {% extends %}  (grades.html:1)
```
**Seuls 2 templates** héritent encore de la base V1 (`grep -rln "extends 'learn/base_student.html'"` → profile + grades).

### Les écrans V2 — tous autonomes (aucun `extends`)
Chacun déclare son propre `<!DOCTYPE html>`, `<head>`, `<body>` :
- `empty_v2.html:1`, `parcours_v2.html:1`, `lecteur_v2.html:1`,
  `quiz_runner_v2.html`, `exam_runner_v2.html:1`, `story_v2.html:2`.

### Pourquoi les V2 sont autonomes (3 raisons techniques observables)
1. **Thème incompatible.** Les V2 sont en **thème sombre** (`<html class="theme-dark">`),
   la base V1 force `bg-[#F0FDF9]` clair (`base_student.html:20`). Hériter
   imposerait le fond clair + le header/nav V1.
2. **Stack incompatible.** Les V2 n'utilisent **ni `output.css` ni `student.css`**
   (Tailwind), seulement du CSS inline + vendored Manrope (`grep output.css
   templates/student_learning/*` → NONE). La base charge les deux (`base_student.html:12-13`).
3. **Chrome applicatif différent.** Les V2 portent leur **propre header + bottom-nav
   à 4 onglets dynamiques** (Parcours/Pratique/Révision/Profil,
   `parcours_v2.html:364-369`), incompatible avec la nav 3-items de la base
   (`base_student.html:79-103`).

> **Signal de refonte :** le designer a fourni une maquette React (cf. `PORTAL_V2_SPEC §1.6`)
> reconstruite « pas copiée » en HTML/Alpine. Plutôt que de plier la maquette dans
> la base V1, l'équipe a recréé chaque écran en page complète. **Le coût** : aucune
> base partagée V2 → duplication massive (cf. §3).

---

## 3. `base_student.html` disséqué + duplication V2

### 3.1 Anatomie de `base_student.html` (145 lignes)

| Zone | Lignes | Contenu |
|---|---|---|
| `<head>` | 3-18 | charset, viewport `maximum-scale=1.0` (zoom bloqué), **Google Fonts Manrope** (`:8-10`), `output.css` + `student.css` (`:12-13`), Alpine `defer` (`:14`), Lucide + `createIcons()` (`:15-16`), `{% block extra_head %}` (`:17`) |
| `<body>` | 20 | `bg-[#F0FDF9] … max-w-md mx-auto` — **conteneur mobile centré** |
| Header | 22-71 | 🔥 streak (`:26-31`), titre cliquable piloté au scroll (`:34-39`), dropdown switch matière Alpine (`:42-69`) |
| Main | 75-77 | `flex-1 pb-20 overflow-y-auto` + `{% block content %}` |
| Bottom-nav | 79-103 | **3 items** : Accueil / Notes / Profil (`text-student-500` actif) |
| Confettis | 105-142 | `window.launchConfetti()` Canvas global, 80 particules |

**Note V1 résiduelle :** ce header (streak + switch matière) a été conçu pour le
**dashboard V1 supprimé**. Sur les 2 écrans qui l'héritent encore (profil, notes),
le switch matière et le titre-au-scroll n'ont **aucun sens** → chrome mort hérité.

### 3.2 Gestion head/scripts par les V2 autonomes — duplication quantifiée

| Aspect | base V1 | parcours_v2 | lecteur_v2 | quiz_runner_v2 | exam_runner_v2 | story_v2 | empty_v2 |
|---|---|---|---|---|---|---|---|
| Police | Google Fonts | vendored | vendored | vendored | vendored | vendored | vendored |
| Tailwind `output.css` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `student.css` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Thème | clair inline body | `theme-dark` bloc `<style>` | `theme-dark` | `theme-dark` | **`:root` (pas theme-dark)** | `theme-dark` | `theme-dark` |
| Alpine | défer global | défer local `:9` | défer local `:9` | local | local | local `:9` | **absent** |
| Lucide | global | local `:8` | local | local | local | local | local `:40` |
| Confetti | global JS | réimplémenté | — | réimplémenté `:760+` | — | réimplémenté `:847` | — |

**Duplication :** le bloc `.theme-dark { --bg … }` (≈ 10 variables CSS) est **copié-collé
dans 4 fichiers** (parcours `:17-26`, lecteur `:16-23`, story, empty `:10-14`). Toute
évolution du thème = 4-5 éditions manuelles. `exam_runner_v2` diverge même de la
convention (cf. §incohérences).

---

## 4. Header / Nav / Footer — desktop & mobile, V1 & V2

> **Tout le portail est mobile-only.** Pas de layout desktop : conteneurs `max-w-md`
> (V1) ou `max-width:480px` (V2 parcours) centrés. Sur desktop = colonne étroite
> centrée sur fond. **Aucun breakpoint desktop** (cf. §8).

### Header
| | V1 (base) | V2 (parcours) | V2 (lecteur) | V2 (exam) |
|---|---|---|---|---|
| Position | `sticky top-0` | flex column header (`appHeader`) | header sticky | header running |
| Gauche | 🔥 streak | bouton « Mes leçons » (library) `:126` | retour `arrow-left` `:62` | — |
| Centre | titre leçon cliquable | titre animé `titleAnim` au scroll `:130` | titre section au scroll `:64` | titre épreuve |
| Droite | switch matière (book-open) | bouton « Lire » → lecteur `:132-142` | TTS + zoom A-/A+ `:67,74-75` | timer-chip `:168` |
| Barre progression | ❌ | ✅ `hdrBar` colorée `:124` | ✅ `:78-80` | ✅ timer |

**Le gamifié a-t-il une nav différente ?** **Oui, radicalement.**
- **V1 streak** dans le header (`base_student.html:26-31`). **Pas de barre XP** dans
  le header V1 (XP affiché seulement sur profil).
- **V2 bottom-nav à 4 onglets dynamiques** Alpine (`parcours_v2.html:260-269`,
  data `:364-369`) : Parcours (`route`), Pratique (`dumbbell`), Révision (`layers`),
  Profil (`user`) — icônes dans pastille dégradée à la couleur de leçon quand actif.
- **V1 bottom-nav à 3 items** statiques (`base_student.html:82-101`) : Accueil /
  Notes / Profil. **Les deux nav ne correspondent pas** (4 onglets V2 ≠ 3 items V1).
- Gamification de nav V2 : **anneaux de passes** autour des nodes quiz
  (`parcours_v2.html:202-212`), badge ✓ vert sur node fait (`:229-231`), label
  « DÉMARRER » bondissant sur node courant (`:214-216`).

### Footer
Aucun footer au sens classique. La bottom-nav fait office de barre d'action permanente.

---

## 5. Liste exhaustive des écrans + rôle

| # | Écran | Fichier | Rôle |
|---|---|---|---|
| 1 | Login | `learn/login.html` | Auth élève par `access_code` + nom de famille |
| 2 | Écran vide | `empty_v2.html` | État zéro-leçon (aucune leçon publiée pour la classe) |
| 3 | Parcours | `parcours_v2.html` | **Carte d'apprentissage** : chemin ondulé SVG, nodes quiz/story/checkpoint, anneaux de passes, sheet de détail |
| 4 | Lecteur | `lecteur_v2.html` | **Lecture « Lire »** : 8 types de blocs, glossaire cliquable, TTS, notes, zoom texte, sommaire |
| 5 | Quiz Runner | `quiz_runner_v2.html` | **Runner de quiz** séquentiel — 13 types, feedback serveur, étoiles, confettis |
| 6 | Exam Runner | `exam_runner_v2.html` | **Examen/checkpoint** chronométré, navigation libre, bilan par notion, verdict admis/échoué |
| 7 | Story | `story_v2.html` | **Récit interactif** type WhatsApp : narration/npc/choice/input/tokens/blank |
| 8 | Profil | `learn/profile.html` | Avatar, niveau, barre XP, streak, stats, grille de badges |
| 9 | Notes & Rangs | `learn/grades.html` | Rang + tendance, notes par matière, bulletins PDF |
| — | `_rcheck.html` | partial | Mini-quiz inline tf/qcm dans le lecteur |

---

## 6. Gamification — XP, badges, niveaux, progression, animations

| Élément | Où | Comment rendu | V1 / V2 |
|---|---|---|---|
| **XP** | profil `:24`, quiz fin `:715` (`+xp`), story score | texte `⭐ {{ total_xp }} XP` (V1) ; `score*10` calculé client (V2 quiz `quiz_runner:734`) | les deux |
| **Niveaux** | profil `:16-18` | badge `gold-500` « Niveau N {nom} » + `level_emoji` | V1 |
| **Barre XP** | profil `:22-34` | dégradé `gold-500→gold-400`, % via `stats.level_pct` | V1 |
| **Streak 🔥** | header V1 `:26-31`, profil `:37-47` | compteur + meilleur streak | V1 |
| **Badges** | profil `:66-76` | grille 3-col, gagné coloré / 🔒 grisé via `dict_key` | V1 |
| **Étoiles** | quiz fin `:707-712`, story | 1-3 ★ selon ratio score (`stars` getter) | V2 |
| **Confettis** | base V1 `launchConfetti():108`, quiz `spawnConfetti():760`, story `:847` | Canvas (V1) **vs** DOM `.confetti-piece` (V2) — **3 implémentations distinctes** | les deux |
| **Anneaux de passes** | parcours `:202-212`, sheet `:291-298` | SVG squircle segmenté, 1 segment = 1 passe | V2 |
| **Node courant pulsant** | parcours `:53-54` (`curGlow`) | `@keyframes` brightness | V2 |
| **Label DÉMARRER** | parcours `:59-64` (`bob`) | bulle blanche bondissante sur node courant | V2 |
| **Badge ✓ done** | parcours `:229-231` | pastille verte `doneBadge` | V2 |
| **Shake node verrouillé** | parcours `:55-56,223-224` | `@keyframes shakeX` au clic sur locked | V2 |
| **XP pill** | sheet `:317` | `+N XP` avec icône gem | V2 |

**Constat clé :** la gamification « identitaire » (XP total, niveaux nommés, badges,
streak) vit **uniquement dans l'écran V1 (profil)**. La gamification « de jeu »
(étoiles, anneaux, pulse, confetti) est **100 % V2**. L'onglet Profil de la nav V2
**pointe vers le profil V1** (rupture de thème, cf. §incohérences). **Aucune barre
XP/niveau dans le chrome V2** — l'élève ne voit son niveau qu'en quittant le thème sombre.

---

## 7. Structure de contenu des écrans clés

### Parcours (`parcours_v2.html`) — carte / chemin
- **Chemin ondulé** : `<svg class="ppath">` + segments `path` (`:176-184`), lit/dim
  selon progression, dasharray pour le futur.
- **Nodes positionnés en absolu** (`:197-233`) : `left/top` calculés serveur (zigzag),
  taille `node_size`, gradient `g0→g1`, ombre portée colorée `glow`.
- **3 types de node** : quiz, story, checkpoint (icône Lucide par type).
- **Séparateurs de leçon** (`:186-194`) pour parcours multi-leçons par matière +
  marqueurs invisibles pour titre-au-scroll (`:198`, IO `:381-395`).
- **Sheet de détail** (bottom-sheet, `:271-346`) : chip type, titre, desc, passes,
  XP, CTA contextuel (quiz/story/exam) + lien « Lire la leçon ».
- **Dropdown matières** (`:145-165`), **jump-to-current** FAB (`:251-256`), toast.

### Quiz Runner (`quiz_runner_v2.html`, 1044 l.) — séquence
- **Shell** `quizShell` (`:751`) : `idx`, `results[]`, `phase` (quiz→done), getters
  `score`/`stars`/`xp`/`endTitle`.
- **13 composants de bloc** Alpine (`blockMcqSingle`, `blockTrueFalse`, … fallback).
- **Phase finale** (`:699-723`) : trophée, étoiles animées, +XP, confettis, retour parcours.
- **Validation serveur** : `postAnswer()` fetch (`:728`) → `{correct, explanation,
  solution, passes_done}`.

### Lecteur (`lecteur_v2.html`, 312 l.)
- **8 types de blocs** : `p` (rich_html glossaire), `def`, `example`, `key`,
  `callout`, `warn`, `reflect` (textarea), `check` (→ `_rcheck.html`).
- **TTS** Web Speech avec surlignage bloc actif (`:290-305`), **glossaire** sheet
  (`:239-253`), **notes** sheet (`:206-237`), **sommaire** (`:181-204`), **zoom**
  texte `--rscale` (`:283-284`).

### Story (`story_v2.html`, 1049 l.)
- **Player WhatsApp** `storyPlayer` (`:765`) : bulles gauche/droite par perso,
  avatars colorés, narration centrée, animation de frappe.
- **6 step types** : narration/npc/choice/input/tokens/blank (`:869+`).
- **Avancement auto** (`advance():865`), score → étoiles, confettis si `done`,
  persistance `persistCompletion()`, particules de fond.

---

## 8. Responsive — mobile-first / tactile (quantifié)

**Le portail est exclusivement mobile, tactile, dark-first (V2).** Il n'y a PAS de
responsive desktop : une seule largeur de colonne centrée.

| Métrique | Valeur |
|---|---|
| Conteneur V1 | `max-w-md` (448px) — `base_student.html:20` |
| Conteneur V2 | `max-width:480px` (parcours), `560px` (lecteur/quiz), `400-520px` (exam), `440px` (empty) — **incohérent entre écrans** |
| `@media` breakpoints | parcours 1, exam 1, story 1, **lecteur 0, quiz 0** — et tous sont `prefers-reduced-motion`, **aucun n'est un breakpoint de largeur** |
| `100dvh` (viewport mobile dynamique) | parcours, lecteur, exam, empty (4 fichiers) |
| `safe-area-inset` (encoche) | quiz (2×), parcours, lecteur, story (notch-aware) |
| `viewport-fit=cover` | tous les V2 (`parcours_v2.html:5` etc.) |
| Zoom utilisateur | **bloqué** : `maximum-scale=1` partout (V1 `:5` + tous V2) — anti-pattern a11y |
| Tactile | `-webkit-tap-highlight-color:transparent` (student.css:34), `:active{transform:scale}` partout, `inputmode="decimal"` (quiz `:578`) |

**Constat :** mobile-first **assumé et soigné** (dvh, safe-area, tap states), mais
**0 breakpoint de largeur** = inutilisable confortablement sur desktop/tablette
(colonne étroite). Largeurs max **divergentes** entre écrans V2 (480/560/520).

---

## 9. Composants — propres au gamifié vs empruntés

### Propres au portail élève V2 (réinventés inline, non partagés)
| Composant | Fichier:ligne | Variante |
|---|---|---|
| Node parcours (squircle SVG) | `parcours_v2.html:218-227` | quiz/story/checkpoint/locked |
| Anneau de passes | `parcours_v2.html:202-212` | continu / segmenté |
| Bottom-sheet détail | `parcours_v2.html:271-346` | locked / unlocked |
| Bottom-nav 4 onglets | `parcours_v2.html:260-269` | actif (pastille dégradée) / inactif |
| Bulle de dialogue | `story_v2.html:503+` | narration / char gauche / char droite |
| Bloc lecture (×8) | `lecteur_v2.html:95-155` | p/def/example/key/callout/warn/reflect/check |
| Bloc quiz (×13) | `quiz_runner_v2.html` | un Alpine.data par type |
| Timer-chip examen | `exam_runner_v2.html:88-90` | normal/warn/low |
| Verdict badge examen | `exam_runner_v2.html:104,310` | admis / à retravailler |
| `_rcheck` mini-quiz | `_rcheck.html` | tf / qcm |

### Empruntés / partagés avec V1
| Composant | Source | Réutilisé par |
|---|---|---|
| `base_student.html` (header+nav) | V1 | profile, grades **seulement** |
| `launchConfetti()` Canvas | base V1 `:108` | profile/grades (mais V2 réimplémente le sien) |
| Barre de note colorée | grades `:60-63` | — |
| Grille de badges | profile `:67-76` | — |

> **Anti-réutilisation :** confettis = **3 implémentations** ; thème sombre = **4 copies** ;
> les blocs lecture et quiz ne sont **pas** partagés malgré recouvrement conceptuel.
> `scrollbar-hide` (student.css:68) n'est plus utilisé QUE par des templates
> **teacher** (`observations.html`, `difficulty_class.html`), plus aucun écran élève.

---

## 10. Patterns Alpine & HTMX + animations CSS

### HTMX
**Absent du portail élève** (`grep htmx templates/student_learning/*` → NONE).
La validation des réponses passe par **`fetch()` natif** (quiz `postAnswer():728`,
exam `submit`), pas par HTMX — divergence avec le reste de l'app qui l'utilise.

### Alpine — state machines (les runners sont 100 % Alpine)
| Composant | Fichier:ligne | État / machine |
|---|---|---|
| `parcours()` | `parcours_v2.html:356-415` | `tab`, `sheet`, `dropdown`, `jumpDir`, IntersectionObserver titre |
| `reader()` | `lecteur_v2.html:260-307` | `active`, `progress`, `scale`, `toc`/`notesOpen`/`term`, TTS queue |
| `quizShell` | `quiz_runner_v2.html:751` | **machine** `phase: quiz→done`, `idx`, `results[]`, getters score/stars/xp |
| `blockBase` factory | `quiz_runner_v2.html:~736` | `checked`/`busy`/`isRight`, `submit()` async, `go()` dispatch event |
| 13× `blockXxx` | `quiz_runner_v2.html:792+` | un Alpine.data par type, héritent `blockBase` |
| `examPlayer` | `exam_runner_v2.html:376-537` | **machine** `phase: intro→running→confirm→result`, timer `setInterval`, `timeLeft`, verdict |
| `storyPlayer` | `story_v2.html:765-1044` | `step`, `history[]`, `typing`, `waiting`, `advance()` auto, sous-états input/tokens/blank |

**Pattern remarquable :** event bus Alpine (`$dispatch('quiz:answered')` →
`quizShell.advance()`) découple bloc ↔ shell — architecture propre. Toute la
correction est **serveur** (anti-triche), conforme `PORTAL_V2_SPEC §3-P2`.

### Animations CSS (où ?)
- **`student.css`** (V1) : `gradientShift`, `flip-card` 3D, **toutes les `story-*`**
  (pop, typing, sheet, stars, pfill) — **toutes orphelines** (les écrans qui les
  utilisaient sont supprimés ; cf. §dette).
- **V2 inline** : `curGlow`/`shakeX`/`bob`/`sheetUp`/`dropIn`/`titleIn` (parcours),
  `fadein`/timer transitions (exam), confetti DOM, frappe (story) — **réécrites
  inline**, doublons conceptuels de `student.css`.
- `prefers-reduced-motion` respecté dans parcours, exam, story, student.css —
  **mais PAS dans lecteur ni quiz** (0 occurrence).

---

## 11. Incohérences (sévérité)

| # | Incohérence | Fichier:ligne | Sévérité |
|---|---|---|---|
| I1 | **Deux design systems** dans un même portail : V2 sombre violet vs V1 clair émeraude. L'onglet « Profil » de la nav V2 ouvre le profil V1 → saut de thème brutal | nav V2 `parcours_v2.html:368` → `learn/profile.html` | **Élevée** |
| I2 | **exam_runner diverge de la convention V2** : pas de `class="theme-dark"`, utilise `:root` avec une **palette différente** (`--bg:#09090E` vs `#0b0b1a`) et `--accent-dk:#4F46E5` au lieu de `#6d28d9` | `exam_runner_v2.html:2,10-16` | **Moyenne** |
| I3 | **Largeurs max divergentes** : 480 (parcours) / 560 (lecteur, quiz) / 400-520 (exam) / 440 (empty) → la colonne « saute » de largeur en navigant | cf. §8 | Moyenne |
| I4 | **Couleur d'accent dupliquée en dur** `#6d28d9` / `#818CF8` dans des dizaines de styles inline V2 au lieu d'une variable | partout V2 | Moyenne |
| I5 | **Zoom bloqué** `maximum-scale=1` sur tous les écrans → a11y (malvoyants) | `base_student.html:5` + tous V2 | Moyenne |
| I6 | **3 implémentations de confettis** (Canvas V1, DOM quiz, DOM story) | `:108`, `:760`, `:847` | Faible |
| I7 | **`prefers-reduced-motion` partiel** : absent de lecteur & quiz (les plus animés) | lecteur, quiz | Faible |
| I8 | Header V1 streak/switch-matière hérité par profil & notes où il est **non fonctionnel** | `base_student.html:22-71` | Faible |

---

## 12. Dette de refonte (V1 résiduel / code mort / divergences spec↔code)

| # | Dette | Fichier:ligne | Sévérité |
|---|---|---|---|
| D1 | **`student.css` quasi-orphelin** : 132 l. dont **seul `scrollbar-hide` est utilisé** (et uniquement par des templates *teacher*). `track-node*`, `learning-path`, `flip-card*`, toutes les `story-*`, `gradientShift` → **0 référence élève** (templates V1 supprimés). Toujours chargé par `base_student.html:13` | `static/css/student.css` | **Élevée** |
| D2 | **Exam runner : 5/13 types seulement** (mcq_single, mcq_multiple, true_false, cloze_test, matching). 8 types manquants vs spec `§3-P2`. Divergence majeure spec↔code | `exam_runner_v2.html:198-244` | **Élevée** |
| D3 | **5 stubs `bientôt`** : header « Lire » fallback (parcours `:138`), onglets non-parcours (`:245`), CTA sheet sans URL (`:328`), CTA exercices lecteur (`:165`) | cf. grep §recherche | **Moyenne** |
| D4 | **Onglets nav Pratique & Révision vides** : la nav 4-onglets V2 n'a qu'1 onglet fonctionnel (Parcours) | `parcours_v2.html:241-247,364-369` | **Moyenne** |
| D5 | **Profil & Notes jamais migrés V2** : restent en thème clair V1, brisent la cohérence visuelle de la refonte | `learn/profile.html`, `learn/grades.html` | **Moyenne** |
| D6 | **Code zigzag V1 « inatteignable » documenté dans la vue** : commentaires `views.py:100` (« retiré au LOT 4 »), helper zigzag `:371,380` conservé | `apps/student_learning/views.py:100,371,380` | Faible |
| D7 | **`PORTAIL_ELEVE.md` périmé** : décrit V1 « Phases 1-11 ✅ Terminées » avec dashboard/lesson/quiz/flashcards V1 — **tous supprimés depuis**. Le doc ne mentionne PAS la refonte V2 | `PORTAIL_ELEVE.md:188-303` | **Moyenne** (doc trompeuse) |
| D8 | **`base_student.html` charge `student.css` mort + Google Fonts** alors que V2 a basculé en vendored | `base_student.html:10,13` | Faible |
| D9 | **`empty_v2.html` n'inclut pas Alpine** mais d'autres V2 oui — incohérence de squelette | `empty_v2.html` (head) | Faible |

---

## 13. Conformité à `PORTAL_V2_SPEC.md` (spec ↔ code)

| Exigence spec | Code | État |
|---|---|---|
| Mobile-first, peu de JS lourd, rendu serveur | conteneurs étroits, vues assemblent nodes serveur | ✅ |
| Séparer contenant (type) / contenu (matière) | quiz runner dispatch par `type` | ✅ |
| Nodes assemblés par le SERVEUR (§3.4) | `views.py:236` build nodes pour `json_script` | ✅ |
| 13 types de quiz (§3-P2) | **quiz_runner : 13/13** ✅ ; **exam_runner : 5/13** ❌ | 🟡 partiel |
| Système de passes (§3.3) anneau segmenté | `parcours_v2.html:202-212,291-298` | ✅ |
| Reading 8 blocs + glossaire `terms` (§3.5) | `lecteur_v2.html` 8 blocs + glossaire | ✅ |
| Story 6 interactions (§3.6) | `story_v2.html` 6 step types | ✅ |
| Exam : timer, bilan par notion, verdict `pass_mark` (§3.7) | `exam_runner_v2.html` intro/running/confirm/result | ✅ |
| Couleurs perso fournies par l'IA (§3.6 note) | `story` consomme `color` perso | ✅ |
| RTL (arabe / fiqh) `direction` (§3.1) | `<html dir>` non observé dans les V2 (toujours `lang="fr"`, pas de `dir`) | ❌ non implémenté |
| Ancien portail « remplacé, pas conservé » (§1.6) | V1 supprimé sauf profil/notes/login | 🟡 quasi |

---

## 14. Résumé chiffré

- **Templates périmètre :** 4 V1 (`learn/`) + 7 V2 + 1 partial (`student_learning/`).
- **Étendent la base V1 :** 2 (profil, notes). **V2 autonomes :** 6.
- **Lignes V2 :** quiz 1044, story 1049, exam 567, parcours 420, lecteur 312,
  empty 42, _rcheck 34 ≈ **3468 lignes** vs base V1 145 l.
- **Quiz types :** runner **13/13**, exam **5/13**.
- **Stubs `bientôt` :** 5. **Onglets nav V2 fonctionnels :** 1/4.
- **`student.css` :** 132 l., **~1 classe vivante** côté élève (`scrollbar-hide`, et hors élève).
- **Confetti :** 3 implémentations. **Thème sombre :** 4 copies inline + 1 divergent (exam).
- **Breakpoints largeur :** 0. **dvh :** 4 fichiers. **safe-area :** 4 fichiers.
- **HTMX :** 0. **Alpine state machines :** ≥ 5 (dont 3 vraies machines à phases).
- **% refonte estimé : ~80 %.**
</content>
</invoke>
