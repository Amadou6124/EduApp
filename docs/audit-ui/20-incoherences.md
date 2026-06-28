# Registre des incohérences — EduApp (audit UI/UX)

> Catalogue consolidé et classé par sévérité, destiné à être corrigé au fil du refonte.
> Chaque entrée : **portail / périmètre · fichier:ligne · constat**. Source détaillée entre crochets
> (ex. `[admin §11 B1]`) renvoie au document de portail correspondant.
>
> Échelle de sévérité normalisée sur l'ensemble des rapports :
> **Bloquant** = piège actif / dette qui contamine tout futur travail · **Majeur** = incohérence
> visible ou structurelle à traiter dans le refonte · **Mineur** = nettoyage cosmétique / dette locale.
> Les sévérités « Élevée / Moyenne / Faible » du portail élève ont été remappées (Élevée→Majeur,
> Moyenne→Majeur ou Mineur selon impact, Faible→Mineur).

## Synthèse quantitative

| Sévérité | Nombre | Dont transversal | Dont portail élève (UI + dette refonte) |
|---|---|---|---|
| 🔴 Bloquant | 3 | 1 | 2 |
| 🟠 Majeur | 21 | 7 | 6 |
| 🟡 Mineur | 30+ | 9 | 6 |
| **Total catalogué** | **~54** | 17 | 14 |

Trois familles dominent : **(1)** un design system « déclaré mais non adopté » (composants `@apply`
court-circuités par du style inline), **(2)** la fragmentation de la couleur de marque et des hex
hardcodés, **(3)** la fracture du portail élève (sous-design-system + dette de refonte V1/V2).

---

## 🔴 Bloquant

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| **BLK-1** | Transversal | `static/css/components.css:1-51` | **Fichier CSS mort et trompeur.** Jamais linké (seul `output.css` est chargé, `base.html:13`), référence le token `brand-blue` **inexistant** dans `tailwind.config.js` (0 occ. dans `output.css`), et **redéfinit** `.btn-primary` / `.input-field` / `.badge-*` avec des signatures **différentes** de la vraie source `input.css` (ex. `px-4 py-2` vs `px-4 py-2.5`). Source de vérité ambiguë : tout dev l'éditant croira agir sur l'UI sans effet. [transversal §12-1 · admin §11 B1] |
| **BLK-2** | Élève | `static/css/student.css` (chargé `base_student.html:13`) | **CSS quasi-orphelin (132 l.).** Seul `scrollbar-hide` est encore utilisé — et uniquement par des templates *teacher*. `track-node*`, `learning-path`, `flip-card*`, toutes les `story-*`, `gradientShift` → **0 référence élève** (les templates V1 qui les utilisaient ont été supprimés). Toujours chargé en prod. [élève §12 D1] |
| **BLK-3** | Élève | `exam_runner_v2.html:198-244` vs `PORTAL_V2_SPEC.md §3-P2` | **Divergence spec↔code majeure :** l'exam runner n'implémente que **5 types de questions sur 13** (mcq_single, mcq_multiple, true_false, cloze_test, matching) ; 8 types spécifiés manquent. Fonctionnalité annoncée mais non livrée — bloque la mise en service complète des examens. [élève §12 D2] |

---

## 🟠 Majeur

### Architecture / chargement des assets

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-1 | Admin (auth) | `accounts/login.html:9-11,16` ; idem `select_school.html`, `portal_coming_soon.html` | **CDN externes sur l'écran de connexion** : Manrope via `fonts.googleapis.com` + **Alpine via `cdn.jsdelivr.net`**, alors que tout le reste est vendored. Dépendance réseau + incohérence d'architecture sur la première page vue. [admin §11 B2] |
| MAJ-2 | Élève | `learn/base_student.html:8-10` | **Police via Google Fonts CDN** alors que `base.html` / `base_parent.html` / `base_superadmin.html` self-hostent Manrope (`vendor/fonts/manrope/`). Régression offline/perf, incohérence d'hébergement. [transversal §12-2 · élève §12 D8] |
| MAJ-3 | Admin | `superadmin/base_superadmin.html` | **Superadmin = portail divergent** : ne charge ni Alpine ni HTMX, pas de recherche, pas de bottom-sheets, navbar `bg-primary-900` propre. Double système de layout à maintenir. [admin §11 B4] |

### Design system « déclaré mais non adopté »

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-4 | Transversal | global | **Composants `@apply` court-circuités par l'inline** : `bg-primary-600` inline **131×** vs `.btn-primary` 62× ; **71 cards inline** vs `.card` (51 fichiers) ; **~387 pills inline** vs `.badge-*` (23). [transversal §12-3, §5] |
| MAJ-5 | Enseignant | `dashboard.html` (0 util.) vs `notes_dashboard.html:22,38,53` | **Sous-utilisation des utilitaires partagés** : dashboard / attendance / difficulty / observations réécrivent les styles à la main alors que `.card`/`.btn-primary`/`.input-field` existent. [enseignant §10-7] |
| MAJ-6 | Parent | `dashboard.html:322`, `bulletins.html:151,156` | **Système de boutons divergent** : `.btn-primary` non utilisé, classes réécrites à la main, rayons `rounded-xl`/`rounded-2xl` mélangés. [parent §11 I3] |

### Couleur / tokens

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-7 | Transversal | global | **Triple expression de la couleur de marque** : `primary` (indigo) vs `indigo-*` (23 occ.) vs `blue-*` (53 occ.) pour la même intention. [transversal §12-4, §3] |
| MAJ-8 | Transversal | 46 fichiers | **78 hex hardcodés distincts**, dont des couleurs qui ont déjà un token : `#4F46E5`×13, `#22C55E`×23, `#EF4444`×21. [transversal §12-5] |
| MAJ-9 | Élève | `learn/*`, `student.css:39-46` | **Palette élève entièrement hors tokens** (violets + ~15 near-black). [transversal §12-6] |

### Accessibilité

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-10 | Transversal | global | **`focus-visible:` totalement absent (0 occ.)** → focus clavier non différencié. [transversal §12-7, §état] |
| MAJ-11 | Transversal | global | **a11y modale partielle** : seulement 3 `role="dialog"` pour ~32 overlays. [transversal §12-8] |
| MAJ-12 | Élève | `base_student.html:5` + tous les V2 | **Zoom bloqué** (`maximum-scale=1`) sur tous les écrans → malvoyants. [élève §11 I5] |

### Responsive / structure

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-13 | Enseignant | `notes_class.html:171,200` vs `base.html:647,751` | **Double breakpoint de bascule concurrent** : `base.html` commute sur `lg` (1024) mais la saisie de notes sur `sm` (640). Entre 640–1024px : tableau desktop + bottom-nav mobile + pas de sidebar. [enseignant §10-1] |
| MAJ-14 | Enseignant | `base.html:647-657` | **Titre de page invisible en mobile enseignant** : le header mobile n'inclut pas `{% block page_title %}` (bloc `hidden lg:flex`). notes_dashboard, observations, notifications n'ont aucun titre visible sur mobile. [enseignant §10-2] |

### Navigation / état actif

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-15 | Admin | `base.html:666` (mobile), `base.html:704` (desktop) | **Cloche notifications = `<button>` inerte** sans action. Affordance trompeuse. [admin §11 B3] |
| MAJ-16 | Parent | dashboard:36 / notes:44 / suivi:49 / payments:46 | **Sélecteur d'enfant codé de 3 façons** (liens serveur `?child=` vs onglets Alpine `x-show`). UX incohérente. [parent §11 I1] |
| MAJ-17 | Parent | notes / annonces / notifications | **Bottom-nav non surlignée** (bloc non surchargé → `active=""`) sur 3 écrans, dont certains sans onglet correspondant. [parent §11 I2] |

### Duplication de logique

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-18 | Enseignant | `difficulty_class.html:35-57` ≡ `difficulty_dashboard.html:41-63` | **`handleScoreUpdate` copié-collé à l'identique** (>20 lignes JS). [enseignant §10-4] |
| MAJ-19 | Enseignant | `notes_class.html:66-68` vs `note_cell.html` (serveur) | **Validation de note divergente** : règle client (mobile, `0–max`) vs serveur (desktop) — risque de désynchronisation. [enseignant §10-12] |

### Cohérence du portail élève

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MAJ-20 | Élève | nav V2 `parcours_v2.html:368` → `learn/profile.html` | **Deux design systems dans un même portail** : V2 sombre violet vs V1 clair émeraude. L'onglet « Profil » ouvre un écran V1 → saut de thème brutal. [élève §11 I1] |
| MAJ-21 | Élève | `parcours_v2.html:241-247,364-369` + 5 stubs « bientôt » | **Nav V2 à 4 onglets dont 1 seul fonctionnel** (Parcours) ; Pratique & Révision vides ; profil & notes jamais migrés en V2. [élève §12 D3, D4, D5] |

---

## 🟡 Mineur

| # | Portail | Fichier:ligne | Constat |
|---|---|---|---|
| MIN-1 | Admin | `400.html`, `403.html`, `404.html`, `schools/announcements/partials/announcement_card.html` | Dérive `indigo-*`/`bg-indigo-600` au lieu de `primary-*`. [admin M1] |
| MIN-2 | Admin | `team_list.html:188,223` (`#F3F0FE`, `#5B21B6`) | Hex codés en dur au lieu d'une classe badge. [admin M2] |
| MIN-3 | Admin | ≥15 fichiers | Boutons/inputs inline réinventés malgré `.btn-*`/`.input-field`. [admin M3] |
| MIN-4 | Admin | `student_list:173`, `payments:85`, `bulletins_main:138` | 3 implémentations d'onglets pour le même visuel. [admin M4] |
| MIN-5 | Admin | `subjects.html`, `school_years.html`, `class_list.html`, toasts… | Mix Lucide + SVG Heroicons inline. [admin M5] |
| MIN-6 | Admin | global | `.data-table` quasi inutilisé (4 occ.) — listes contournent le composant table. [admin M6] |
| MIN-7 | Admin | ~10 instances, drawers `sm:w-[480px]`…`[680px]` | Modales/drawers dupliqués sans partial commun, largeurs ad-hoc. [admin M7] |
| MIN-8 | Admin | `400/403/404` vs `500.html` | Pages d'erreur 400/403/404 héritent de `base.html` (sidebar + header complets) tandis que `500.html` est autonome. [admin M8] |
| MIN-9 | Admin | ~73 occ. ; `.card` `p-4/p-5/p-6` | États vides non factorisés ; padding `.card` non standardisé. [admin M9] |
| MIN-10 | Enseignant | `attendance_class.html:198-234` | Bouton « enregistrer » dupliqué mobile/desktop. [enseignant §10-3] |
| MIN-11 | Enseignant | `notes_class.html:203` / `notes_dashboard.html:87` / `observations.html:56` | 3 mécanismes d'onglets différents (Alpine+HTMX / liens / Alpine client). [enseignant §10-5] |
| MIN-12 | Enseignant | `notes_table.html:103-105,227`, `note_cell.html:77-80` | SVG inline dans notes/ alors que le reste est Lucide. [enseignant §10-6] |
| MIN-13 | Enseignant | `dashboard.html:47` vs `difficulty_student_card.html:5` | Rayons de carte incohérents (`rounded-2xl` vs `rounded-xl` vs `.card`). [enseignant §10-8] |
| MIN-14 | Enseignant | `unit_lessons_edit.html:10-15` | Cibles tactiles < 44px (boutons ▲▼ `w-7 h-6`, chips `py-1.5`). [enseignant §10-9] |
| MIN-15 | Enseignant | `difficulty_class.html:42-56` | Manipulation DOM impérative (classList/textContent) au lieu de bindings Alpine. [enseignant §10-10] |
| MIN-16 | Enseignant | `attendance_class.html:116`, `notifications.html:55` | `top` sticky en dur non aligné aux hauteurs de header réelles. [enseignant §10-11] |
| MIN-17 | Parent | dashboard:377-394 / suivi:168-196 | Palettes des types d'observation divergentes (behaviour `orange` vs `amber`, academic `blue` vs `indigo`). [parent I4] |
| MIN-18 | Parent | annonces:14 vs payments:16 | Largeur du spacer header variable (`w-9` vs `w-14`) → titre non centré sur annonces. [parent I5] |
| MIN-19 | Parent | bottom_nav:1 | Commentaire d'en-tête obsolète (4 valeurs documentées vs 5 items). [parent I6] |
| MIN-20 | Parent | base_parent:82 | Store Alpine `parent.activeChildId` déclaré jamais lu (code mort). [parent I7] |
| MIN-21 | Parent | announcement_card / dashboard:374 / suivi:165 | Pattern « Lire la suite » dupliqué 3× au lieu d'un partial. [parent I8] |
| MIN-22 | Parent | base_parent:26 ; notifications:66 / annonces:39 | `bg-[#F8F9FC]` + `top-14` arbitraires au lieu de tokens. [parent I9] |
| MIN-23 | Parent | base_parent:3,7 | Pas de `<title>` traduisible ni `lang` dynamique (codé `fr`) alors que l'admin gère i18n. [parent I10] |
| MIN-24 | Élève | `exam_runner_v2.html:2,10-16` | Exam runner diverge de la convention V2 (`:root` au lieu de `.theme-dark`, palette `#09090E`/`#4F46E5`). [élève I2] |
| MIN-25 | Élève | cf. §8 | Largeurs max divergentes (480/560/400-520/440) → la colonne « saute » en navigant. [élève I3] |
| MIN-26 | Élève | partout V2 | Accent `#6d28d9`/`#818CF8` dupliqué en dur dans des dizaines de styles inline. [élève I4] |
| MIN-27 | Élève | `:108`, `:760`, `:847` | 3 implémentations de confettis (Canvas V1, DOM quiz, DOM story). [élève I6] |
| MIN-28 | Élève | lecteur, quiz | `prefers-reduced-motion` absent des écrans les plus animés. [élève I7] |
| MIN-29 | Élève | `base_student.html:22-71` | Header V1 streak/switch-matière hérité par profil & notes où il est non fonctionnel. [élève I8] |
| MIN-30 | Élève | `empty_v2.html` (head) | N'inclut pas Alpine alors que d'autres V2 oui. [élève D9] |
| MIN-31 | Élève | `apps/student_learning/views.py:100,371,380` | Code zigzag V1 « inatteignable » conservé + commentaires de lot. [élève D6] |
| MIN-32 | Élève | `PORTAIL_ELEVE.md:188-303` | Doc périmée : décrit un V1 « terminé » entièrement supprimé, ne mentionne pas la V2. [élève D7] |
| MIN-33 | Transversal | global | 228 tailles typo arbitraires `text-[10px]`(160)/`text-[11px]`(59) doublant le palier `2xs`. [transversal §12-9] |
| MIN-34 | Transversal | global | Ombres `xl`/`2xl` (36) hors config (sm/md/lg seulement). [transversal §12-10] |
| MIN-35 | Transversal | `input.css` | Classes mortes : `btn-gold`, `skeleton`, `form-label/helper/error`, `badge-info` (0 occ.). [transversal §12-11] |
| MIN-36 | Transversal | global | Alias sémantiques `success/warning/danger/info` quasi inutilisés au profit de `green/amber/red` bruts. [transversal §12-12] |
| MIN-37 | Transversal | parent/élève | 3 implémentations de barre de progression (`bar-fill`, `story-pfill`, `[data-bar]`). [transversal §12-13] |
| MIN-38 | Transversal | 20 fichiers | Emoji vs Lucide pour mêmes sémantiques (`✓` vs `check`). [transversal §12-14] |
| MIN-39 | Transversal | global | `rounded-md` (36) hors convention de rayons. [transversal §12-15] |
| MIN-40 | Admin | `base.html` | Markup bottom-sheet dupliqué 3× dans base.html. [transversal §12-16] |

---

## Lecture pour le refonte

- **Quick wins à coût quasi nul** (supprimer la dette morte) : BLK-1, BLK-2, MIN-20, MIN-31, MIN-32, MIN-35.
- **Doivent être tranchés AVANT d'écrire le moindre composant du nouveau système** : BLK-1 (source de vérité CSS), MAJ-4 (inline vs `@apply`), MAJ-7/MAJ-8 (couleur de marque unique), MAJ-2/MAJ-1 (politique d'assets self-hosted).
- **Chantier à part, piloté par la roadmap produit, pas par le design** : tout le bloc élève V1/V2 (BLK-3, MAJ-20, MAJ-21, MIN-24→MIN-32) — voir `30-recommandation-architecture.md`.
