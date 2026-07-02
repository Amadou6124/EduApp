# Audit UI/UX — Portail Enseignant (EduApp)

> Audit **lecture seule**. Aucun fichier d'application modifié. Stack : Tailwind (`static/css/output.css`), Alpine.js, HTMX, Chart.js, Lucide, police Manrope.
> Périmètre : `templates/teachers/`, `templates/lessons/`, `templates/notes/` (+ `partials/`). Template de base partagé : `templates/base.html`.
> Date : 2026-06-28.

---

## 0. Chiffres clés

| Métrique | Valeur |
|---|---|
| Fichiers analysés (scope) | 24 templates (3 678 lignes) |
| Pages full (`{% extends base.html %}`) | 12 |
| Partials inclus | 9 |
| Blocs `base.html` surchargés par l'enseignant | 6 (`title`, `page_title`, `page_subtitle`, `header_actions`, `breadcrumb`, `extra_head`) |
| Blocs `x-data` (scope) | 14 fichiers |
| Attributs `hx-*` (scope) | ~57 sur 9 fichiers |
| Icônes Lucide (scope) | 136 occurrences |
| SVG inline (scope) | 8 (concentrés dans notes/) |
| Touch targets `min-h-[44/48/52/56px]` (scope) | 11 |
| `<footer>` dans le scope | **0** (aucun footer ; le rôle est tenu par la bottom-nav mobile) |
| Composant `.card` (tout le projet) | 87 usages |

---

## 1. Arborescence des templates

| Page (URL logique) | Fichier | extends | includes / partials |
|---|---|---|---|
| Tableau de bord | `teachers/dashboard.html` | base.html | — |
| Absences (liste classes) | `teachers/attendance_list.html` | base.html | — |
| Absences (émargement classe) | `teachers/attendance_class.html` | base.html | — |
| Suivi difficulté (toutes classes) | `teachers/difficulty_dashboard.html` | base.html | `difficulty_student_card`, `quick_assessment_form` |
| Suivi difficulté (classe) | `teachers/difficulty_class.html` | base.html | `difficulty_student_card`, `quick_assessment_form` |
| Mes observations | `teachers/observations.html` | base.html | — |
| Notifications | `teachers/notifications.html` | base.html | — |
| Fiche élève | `teachers/student_detail.html` | base.html | `observation_form` |
| Mes élèves | `teachers/students_list.html` | base.html | — |
| Mes unités (liste) | `lessons/unit_list.html` | base.html | — |
| Unité (détail) | `lessons/unit_detail.html` | base.html | `unit_status` → `unit_lessons_edit`, `deploy_card` |
| Importer un document | `lessons/unit_upload.html` | base.html | — |
| Dashboard notes | `notes/notes_dashboard.html` | base.html | `class_progress_card` |
| Saisie notes (classe) | `notes/notes_class.html` | base.html | `notes_mobile_input` (mobile), `notes_table` → `note_cell` (desktop) |

Partials et leur consommateur :

| Partial | Inclus par | Rôle |
|---|---|---|
| `teachers/partials/difficulty_student_card.html` | difficulty_class, difficulty_dashboard | carte élève en difficulté (mobile + accordéons) |
| `teachers/partials/observation_form.html` | student_detail | panel slide-from-right création observation |
| `teachers/partials/quick_assessment_form.html` | difficulty_class, difficulty_dashboard | panel slide-from-right éval rapide |
| `notes/partials/class_progress_card.html` | notes_dashboard | carte progression notes par classe |
| `notes/partials/notes_table.html` | notes_class (desktop) | tableau de saisie + Alpine `notesTable` |
| `notes/partials/note_cell.html` | notes_table (boucle) | cellule note éditable HTMX |
| `notes/partials/notes_mobile_input.html` | notes_class (mobile) | clavier numérique mono-élève |
| `lessons/partials/unit_status.html` | unit_detail | bandeau + checklist + action (polling HTMX) |
| `lessons/partials/unit_lessons_edit.html` | unit_status (si draft) | édition inline des leçons (HTMX) |
| `lessons/partials/deploy_card.html` | unit_detail | carte déploiement classe (toggle HTMX) |

---

## 2. Headers (desktop ET mobile)

Le header est défini dans `base.html` `<header>` (ligne 579) avec **un header mobile dédié à l'enseignant** distinct des autres rôles.

### 2.1 Header mobile ENSEIGNANT (`base.html:582-644`)
Bloc `flex lg:hidden`, `min-h-[56px]`, structure à 3 zones :

| Zone | Élément | Réf |
|---|---|---|
| Gauche | Avatar (initiale) → `settings:general`, `w-9 h-9 rounded-full bg-primary-600` | `base.html:586-590` |
| Centre | Nom école, dropdown switch-school si `user_memberships` (chevron + menu Alpine `schoolMenu`) | `base.html:593-628` |
| Droite | Cloche notifications → `teacher:notifications` + badge rouge `teacher_unread_count` | `base.html:631-642` |

Particularité : ce header mobile enseignant **ne contient pas** le titre de page. Le titre vient ensuite via le bloc générique `hidden lg:flex` (donc absent en mobile enseignant) — la majorité des pages enseignant reposent sur leur propre titre intégré au contenu ou au `page_title` qui n'apparaît qu'en desktop. Voir §10 (incohérences).

### 2.2 Header desktop (tous rôles, `base.html:646-726`)
Bloc `hidden lg:flex` pour l'enseignant (`{% if request.role == 'teacher' %}hidden lg:flex{% endif %}`, ligne 647). Composé de :

| Élément | Réf |
|---|---|
| `{% block breadcrumb %}` (bouton retour) | `base.html:653` |
| `<h1>` `{% block page_title %}` — `text-lg lg:text-2xl` | `base.html:655` |
| `{% block page_subtitle %}` (`hidden lg:block`) | `base.html:656` |
| `{% block header_actions %}` (actions à droite) | `base.html:681` |
| Badge année `badge_year` | `base.html:682-690` |
| Cloche notifications enseignant | `base.html:691-702` |

Header sticky : `sticky top-0 z-20` (ligne 579).

### 2.3 Surcharges de header par page enseignant

| Page | breadcrumb | page_title | header_actions |
|---|---|---|---|
| dashboard | — | « Bonjour {{first_name}} » (`dashboard.html:15`) | avatar coloré (`dashboard.html:7-12`) |
| attendance_class | bouton retour (`:8`) | nom classe | `<input type="date">` (`:18-26`) |
| attendance_list | — | « Absences » + subtitle | — |
| difficulty_class | bouton retour (`:6`) | nom classe + subtitle | — |
| difficulty_dashboard | bouton retour (`:6`) | « Mes élèves » + subtitle dynamique | — |
| observations | — | « Mes observations » + count | — |
| notifications | — | « Notifications » | form « Tout lire » (`:17-27`) |
| student_detail | bouton retour (`:6`) | nom élève + classe | — |
| students_list | — | « Mes élèves » + count | — |
| notes_class | — | breadcrumb custom dans `page_title` (retour + classe + période, `:125-138`) | badge « Saisie ouverte/fermée » (`:140-152`) |
| notes_dashboard | — | « Notes et évaluations » | — |
| unit_* | — | titre simple | — |

---

## 3. Footers (desktop ET mobile)

- **Aucun élément `<footer>`** dans le scope ni dans `base.html`. Vérifié par grep : les seuls `footer` du projet sont dans les PDF (`bulletins/pdf/`, `payments/pdf/`) et la barre reçu paiements (hors scope).
- **Substitut mobile = bottom navigation** fixe (`base.html:751`, `lg:hidden fixed bottom-0`, `min-h-[68px]`, `rounded-t-2xl`, ombre haute). Voir §4.
- **Substituts de « pied » contextuels** dans certaines pages :
  - `notes_table.html:207-233` : barre d'actions de bas de tableau (compteur + raccourci clavier + bouton « Ajouter une évaluation »).
  - barre d'action enregistrer fixe en bas (`attendance_class.html:198-216` mobile / `219-234` desktop).
  - pied du bottom-sheet « Plus » enseignant : identité + déconnexion (`base.html:974-988`).

---

## 4. Navigation

### 4.1 Sidebar desktop enseignant (`base.html:92-155`)
6 items, collapsible (`$store.sidebar.open`, largeur `w-64` ↔ `w-16`). Visible `hidden lg:flex` uniquement.

| # | Libellé | URL | Icône Lucide | Actif si |
|---|---|---|---|---|
| 1 | Mon tableau de bord | `teacher:dashboard` | layout-dashboard | `app_name == 'teacher'` |
| 2 | Mes unités | `lessons:unit-list` | sparkles | url_name in unit-list/detail/upload |
| 3 | Mes notes | `notes:dashboard` | book-open | `app_name == 'notes'` |
| 4 | Absences | `teacher:attendance-list` | calendar-x | url_name attendance-list/class |
| 5 | Suivi élèves | `teacher:difficulty` | alert-triangle | url_name difficulty/difficulty-class |
| 6 | Mes élèves | `teacher:students` | users | url_name students/student-detail |

État actif : `bg-primary-50 text-primary-700 font-semibold`.

### 4.2 Bottom nav mobile enseignant (`base.html:759-819`)
4 items + bouton « Plus ». `flex-1` chacun, `min-h-[68px]`.

| Item | URL | Icône | Actif |
|---|---|---|---|
| Accueil | `teacher:dashboard` | layout-dashboard | dashboard uniquement |
| Notes | `notes:dashboard` | book-open | `app_name == 'notes'` |
| Absences | `teacher:attendance-list` | calendar-x | attendance-list/class |
| Plus | (bottom-sheet) | menu | — |

Indicateur actif : pastille `bg-primary-600/10 rounded-xl` autour de l'item.
**Note** : « Suivi élèves », « Mes élèves » et « Mes unités » ne sont PAS dans la bottom-nav — ils sont relégués au bottom-sheet « Plus » (`base.html:969-971`). La sidebar desktop expose 6 items, la bottom-nav mobile seulement 3 directs.

### 4.3 Bottom-sheet « Plus » enseignant (`base.html:924-993`)
Modal slide-up Alpine (`$store.teacherMoreSheet`), `role="dialog"`, focus-trap (`$nextTick focus`), `escape` ferme, `overflow-hidden` body. Contenu :
- Section « Navigation » : Mes élèves, Suivi difficulté, Mes unités (classe `.sheet-item`).
- Pied : identité (avatar + nom + « Enseignant ») + bouton « Se déconnecter » (rouge).

### 4.4 Fils d'Ariane / boutons retour
- Via `{% block breadcrumb %}` : attendance_class, difficulty_class, difficulty_dashboard, student_detail (bouton flèche `arrow-left`).
- Custom dans le contenu : `notes_class.html:125-138` (retour + classe + période), `notes_class.html:157-166` (fil d'Ariane période desktop only `hidden sm:flex`), `lessons/unit_detail.html:10-13` (« ← Mes unités »), unit_upload (fil d'Ariane multi-étapes Alpine `:114-118`, `:156-162`).

### 4.5 Onglets internes propres à l'enseignant

| Lieu | Type | Réf |
|---|---|---|
| notes_class desktop : onglets matières | Alpine `activeTab` + HTMX `hx-get` swap tableau | `notes_class.html:203-222` |
| notes_dashboard : onglets périodes | liens `<a href>` (rechargement) | `notes_dashboard.html:87-101` |
| difficulty_class : filtres niveau (5 tabs colorés) | liens `?level=` (rechargement) | `difficulty_class.html:73-135` |
| observations : filtres type (5) + statut (5) | boutons Alpine `activeType`/`activeStatus` (filtrage client) | `observations.html:56-137` |

**Incohérence d'implémentation des onglets** : 3 mécanismes différents (Alpine+HTMX, liens reload, Alpine client). Voir §10.

---

## 5. Liste exhaustive des écrans

| Écran | Rôle fonctionnel |
|---|---|
| dashboard | Accueil mobile-first : contexte du jour, 4 stats (classes, élèves, %notes, absences), cartes classes avec progression, actions rapides, observations récentes |
| attendance_list | Liste des classes du jour avec avancement émargement (fait/en attente) |
| attendance_class | Émargement : grille d'élèves tap-to-cycle (présent→absent→retard), compteur sticky, enregistrement HTMX |
| difficulty_dashboard | Vue agrégée multi-classes en accordéons (critiques/attention/à surveiller) + éval rapide |
| difficulty_class | Vue par classe : tableau desktop / cartes mobile, filtres par niveau de risque + éval rapide |
| observations | Liste filtrable des observations saisies (type, statut lu/partagé/privé, recherche) |
| notifications | Notifications groupées par date, suppression/clear HTMX |
| student_detail | Fiche élève : identité, notes par matière, observations + panel création observation |
| students_list | Annuaire élèves groupé par classe, recherche client |
| notes_dashboard | Pilotage notes : sélecteur année, 4 stats, onglets périodes, cartes progression par classe |
| notes_class | **Saisie des notes** — desktop tableau / mobile clavier numérique (cas responsive clé, §6.2) |
| unit_list | Liste des unités pédagogiques v2 (statut prêtes/brouillon) |
| unit_detail | Détail unité : statut génération IA (polling), édition leçons (draft), déploiement aux classes |
| unit_upload | Studio IA en 3 étapes (classe → matière → document) avec drag&drop |

---

## 6. Structure de contenu des pages clés

### 6.1 Dashboard enseignant (`dashboard.html`)
Conteneur `max-w-2xl mx-auto`, mobile-first sans aucun breakpoint (sm/md/lg = 0). 5 sections :
1. Bandeau contexte du jour (gradient indigo `#4F46E5→#6366F1`, `:24-40`).
2. Stats `grid grid-cols-2 gap-3` (4 cartes, `:45-83`) — couleur conditionnelle sur %notes et absences.
3. Cartes classes (`:91-176`) : nom + badge niveau, chips matières/coeff, barre progression notes, 2 boutons (« Saisir notes » primary / « Absences » outline, `min-h-[44px]`).
4. Actions rapides (`:192-230`) : 3 liens `min-h-[56px]`.
5. Observations récentes (`:235-276`) + état vide.

### 6.2 Saisie de notes — DESKTOP vs MOBILE (cas responsive central)

Le routeur responsive est dans `notes_class.html` :
- `<div class="block sm:hidden">` → mobile (`:171-195`)
- `<div class="hidden sm:block">` → desktop (`:200-246`)

Breakpoint de bascule : **`sm` (640px)** — pas `lg`. Deux interfaces **entièrement distinctes**, pas une simple adaptation CSS.

| Aspect | DESKTOP (`notes_table.html` + `note_cell.html`) | MOBILE (`notes_mobile_input.html`) |
|---|---|---|
| Paradigme | Tableau matriciel (élèves × colonnes de notes) | **1 élève à la fois**, plein écran |
| Saisie | `<input type="text">` natif par cellule (`note_cell.html:50-69`) | **Clavier numérique custom 3×4** (`notes_mobile_input.html:99-112`) |
| Lignes / cible | toutes les lignes visibles, scroll horizontal `overflow-x-auto`, colonne élève sticky | carte centrale unique avec avatar 80px, note `text-5xl font-black` |
| Navigation | Tab inter-cellules, recherche élève | flèches prev/next + **swipe tactile** (`notes_class.html:108-118`) + points indicateurs (`:127-139`) |
| Persistance | HTMX `hx-post` par cellule sur `change`/`Enter`, swap `outerHTML` de la cellule | `htmx.ajax POST swap:none` + maj état Alpine local |
| Moyenne | recalcul réactif Alpine `getStudentAvg()` (`notes_table.html:89-92,191`) | barre de progression `notedCount/total` (`notes_mobile_input.html:21-35`) |
| Feedback succès | flash vert sur la cellule (`note_cell.html:35-40`) | toast « Saisie terminée ✓ » + redirection (`notes_class.html:91-95`) |
| Validation note | côté serveur (réponse HTMX) | **côté client** `0–max` (`notes_class.html:66-68`) avec message erreur inline |
| Fin de saisie | reste sur la page | `setTimeout 700ms` → reload page classe (recalcul moyennes serveur) |
| Onglets matières | oui (`hx-get`) | non — la matière active est passée en contexte |
| Stats classe | 3 badges moy/meilleur/faible (`notes_table.html:120-141`) | absent |

C'est la divergence desktop/mobile la plus forte du portail : deux UX, deux modèles de données JS, deux stratégies HTMX. La cohérence visuelle est assurée par la couleur `primary-600` et les avatars, mais le code est dupliqué fonctionnellement.

`note_cell.html` gère 3 états : lecture seule (`:16-29`), édition (`:30-82`), note annulée (`line-through`, `disabled`). Champs cachés (csid/studentid/periodid/position) + indicateur spinner `htmx-indicator`.

### 6.3 Suivi des difficultés (`difficulty_class.html` + `difficulty_dashboard.html`)
- 4 niveaux de risque colorés : critical(rouge) / warning(ambre) / watch(jaune) / good(vert), appliqués bg+border+text.
- difficulty_class : **tableau desktop** (`hidden lg:block`, `:147-248`) avec barre de score, tendance ↑↓→, matières faibles ; **cartes mobile** (`lg:hidden`, `:251-255`) via partial.
- difficulty_dashboard : **accordéons par classe** (Alpine `open`, ouvert si critiques), sections critiques/attention/à surveiller.
- Mise à jour réactive : fonction `handleScoreUpdate` (dupliquée à l'identique dans les 2 fichiers, `difficulty_class.html:35-57` ≡ `difficulty_dashboard.html:41-63`) écoute `@score-updated.window` et repeint la carte sans reload.
- Action commune : panel « Éval rapide » (`quick_assessment_form.html`) déclenché par `openQA()`.

### 6.4 Présences / émargement (`attendance_class.html`)
- Alpine `attendanceGrid` : cycle d'état tap (present→absent→late, `:43-49`), couleurs de carte/avatar/badge calculées JS.
- Compteur sticky `sticky top-14 sm:top-16` (présents/absents/retards, `:116-138`).
- Grille `grid-cols-3 sm:grid-cols-4` (`:144`).
- Bouton enregistrer **dupliqué** mobile fixe (`fixed bottom-16`, `:198-216`) vs desktop inline (`:219-234`) — même logique, même libellé, 2 markups.
- Soumission HTMX `hx-post hx-swap=none`, payload JSON des seuls non-présents (`:79-85`), puis redirection après `attendance-saved`.

### 6.5 Observations (`observations.html`)
- Filtrage 100 % client Alpine : tableau `allObs` sérialisé en JS (`:15-21`), fonction `visible()` croisant type × statut × recherche.
- 2 rangées de filtres scrollables (`overflow-x-auto scrollbar-hide`) : type (5, couleurs distinctes) + statut (5).
- Cartes observation : badge type + badge statut (priorité Privée > Partagé > Lu > En attente), nom élève, extrait `line-clamp-2`, indicateur « message parent reformulé ».

---

## 7. Responsive

### 7.1 Breakpoints utilisés (scope)
Tailwind par défaut : `sm`=640, `md`=768, `lg`=1024, `xl`=1280.

| Fichier | sm | md | lg | xl |
|---|---|---|---|---|
| dashboard.html | 0 | 0 | 0 | 0 (100 % mobile-first) |
| notes_class.html | 3 | 0 | 0 | 0 |
| notes_table.html | 0 | 0 | 0 | 0 |
| notes_mobile_input.html | 1 | 0 | 0 | 0 |
| attendance_class.html | 2 | 0 | 5 | 0 |
| difficulty_class.html | 0 | 0 | 2 | 0 |
| unit_upload.html | 1 | 0 | 1 | 0 |

Observation : **deux breakpoints structurants concurrents** :
- `base.html` bascule desktop/mobile sur **`lg` (1024px)** (sidebar `hidden lg:flex`, header enseignant `hidden lg:flex`, bottom-nav `lg:hidden`).
- la **saisie de notes** bascule sur **`sm` (640px)** (`block sm:hidden` / `hidden sm:block`).

Conséquence : entre 640px et 1024px (tablette portrait), l'utilisateur a déjà le **tableau desktop de notes** mais conserve la **bottom-nav mobile** et **pas de sidebar**. Le fil d'Ariane période est aussi `hidden sm:flex` (donc visible sur tablette mais le titre de header reste masqué jusqu'à lg). Voir §10.

### 7.2 Différences mobile/desktop par écran (quantifié)

| Écran | Stratégie responsive | Markup dupliqué ? |
|---|---|---|
| notes_class | 2 UI complètes (sm) | Oui (table vs clavier) |
| difficulty_class | table (lg) vs cards (lg:hidden) | Oui |
| attendance_class | grille `grid-cols-3 sm:grid-cols-4` + bouton save dupliqué (lg) | Oui (bouton) |
| student_detail | bouton « + Observation » fixe mobile vs inline (`sm:static`, `:144`) | Non (1 markup, classes conditionnelles) |
| notes_dashboard | grille `grid-cols-2 lg:grid-cols-4`, cartes `md:grid-cols-2 xl:grid-cols-3` | Non |
| dashboard | mobile-only, `max-w-2xl` centré sur desktop | Non |
| observations / notifications | mobile-only `max-w-2xl`, padding bas `pb-24 lg:pb-8` | Non |
| panels (obs/QA) | `w-full sm:w-[420px]`, ancrage `lg:top-[64px] bottom-[68px] lg:bottom-0` | Non |

---

## 8. Composants

### 8.1 Inventaire

| Composant | Variantes constatées | Réf représentatives |
|---|---|---|
| Boutons | `.btn-primary` (partagé, util CSS) ; nombreux boutons **ad-hoc** Tailwind ; tap-cards | `quick_assessment_form.html:184` (btn-primary) vs `dashboard.html:157-171` (ad-hoc) |
| Inputs | `.input-field` (partagé) ; inputs ad-hoc Tailwind ; `<input type="date">` ; clavier custom | `notes_dashboard.html:38` (input-field) vs `observations.html:145-149` (ad-hoc) |
| Cards | `.card` (partagé) ; cartes ad-hoc `bg-white rounded-2xl border` | `notes_dashboard.html:53` (.card) vs `dashboard.html:47` (ad-hoc) |
| Modals / panels | bottom-sheet (base) ; **slide-from-right** (obs, QA) ; confirmation inline | `observation_form.html:22-32`, `quick_assessment_form.html:23-34` |
| Tables | notes (sticky col), difficulté desktop | `notes_table.html:144-205`, `difficulty_class.html:147-248` |
| Badges | niveau classe (7 couleurs), risque (4), statut obs (5), saisie ouverte/fermée, prête/brouillon | `class_progress_card.html:19-39`, `difficulty_student_card.html:5-9` |
| Toasts | événement `show-toast` + store (base) | `notes_class.html:91-93` |
| Onglets | 3 implémentations (cf §4.5) | — |
| États vides | très nombreux, pattern récurrent icône+titre+sous-texte(+CTA) | `notes_class.html:230-243`, `students_list.html:86-90`, `observations.html:42-49` |
| Barres de progression | notes, difficulté, upload étapes, génération IA | `dashboard.html:143-150`, `unit_upload.html:52-55`, `unit_status.html:14-17` |
| Avatars | initiales colorées `get_avatar_colors` | `student_detail.html:25-29`, `attendance_class.html:154-158` |

### 8.2 Cohérence

| Point | Constat |
|---|---|
| Couleur primaire | cohérente : `primary-600` partout (boutons, actifs, accents) |
| Rayon de carte | **incohérent** : `rounded-2xl` (dashboard, attendance) vs `rounded-xl` (difficulty cards) vs `.card` (rayon CSS partagé, valeur définie ailleurs) |
| Utilitaires partagés vs ad-hoc | `.btn-primary`/`.card`/`.input-field` existent mais **sous-utilisés dans le scope enseignant** : le dashboard et la plupart des écrans enseignant réécrivent les styles à la main. À l'inverse notes_dashboard utilise `.card`/`.input-field`/`.btn-primary`. |
| Icônes | mix **Lucide (136)** et **SVG inline (8, dans notes/)** — incohérence locale, voir §10 |
| Touch targets | `min-h-[44px]` appliqué de façon irrégulière (11 occurrences scope) ; certaines cibles tactiles (chips, petits boutons ▲▼ `w-7 h-6` dans unit_lessons_edit) sont sous 44px |

---

## 9. Patterns HTMX et Alpine récurrents

### 9.1 HTMX (détail fichier:ligne)

| Pattern | Réf | hx-trigger | hx-swap | hx-target |
|---|---|---|---|---|
| Sauvegarde note (cellule) | `note_cell.html:64-69` | `change, keydown[key=='Enter']` | `outerHTML` | `closest td` (+ `hx-include="closest td"`, `hx-indicator`) |
| Ajouter une colonne notes | `notes_table.html:222-226` | (clic) | `outerHTML` | `closest [x-data]` (+ `hx-vals current_columns`) |
| Switch onglet matière | `notes_class.html:212-215` | `hx-get` (clic) | `innerHTML` | `#notes-table-container` (+ `hx-push-url`) |
| Sauvegarde émargement | `attendance_class.html:189-191` | (submit) | `none` | — |
| Création observation | `observation_form.html:48-51` | (submit) | `none` | `hx-on::after-request` → dispatch close |
| Éval rapide | `quick_assessment_form.html:50-52` | (submit) | `none` | — |
| Suppression notif | `notifications.html:110-116` | (clic) | `outerHTML swap:300ms` | `#notif-{{id}}` |
| Polling statut génération | `unit_status.html:1-3` | `every 3s` (si actif) | `outerHTML` | `this` |
| Lancer génération | `unit_status.html:108` | `hx-post` | (défaut) | — |
| Déployer/retirer leçon | `deploy_card.html:20-23` | (clic) | `outerHTML` | `#deploy-card-{{id}}` |
| Renommer leçon inline | `unit_lessons_edit.html:23-25` | `change, keydown[Enter]` | `outerHTML` | `#unit-lessons-edit` |
| Monter/descendre/fusionner/supprimer leçon | `unit_lessons_edit.html:12-15,31-33,41` | (clic) | `outerHTML` | `#unit-lessons-edit` (+ `hx-confirm`, `hx-vals`) |
| `htmx.ajax` programmatique (mobile notes) | `notes_class.html:72-82` | JS | `none` | source `document.body` |

Header CSRF global : `base.html:30` (`hx-headers` sur `<body>`), redoublé localement sur certains partials (deploy_card, unit_lessons_edit, notifications).

Patterns dominants : **swap `outerHTML` ciblé sur un id/`closest`** (édition optimiste in-place) et **`swap=none` + événement** (formulaires en panel). Le **polling `every 3s`** sur unit_status est le seul polling du portail.

### 9.2 Alpine (détail)

| Pattern | Réf |
|---|---|
| Store global sidebar/sheets | `base.html` `$store.sidebar`, `$store.teacherMoreSheet` (l.812, 926) |
| `x-data` composant de table (notes) | `notes_table.html:42-94` (`notesTable`, recalc moyennes) |
| `x-data` fonction globale `mobileNoteInput` | `notes_class.html:28-120` (clavier, swipe, save) |
| `x-data` grille émargement | `attendance_class.html:35-97` |
| `x-data` filtres client (observations) | `observations.html:11-37` |
| `x-data` recherche client (students_list) | `students_list.html:11-14` |
| `x-data` wizard 3 étapes (upload) | `unit_upload.html:9-32` |
| Panels `x-show` + `x-transition` slide | `observation_form.html:22-32`, `quick_assessment_form.html:23-34` |
| `@score-updated.window` repaint manuel DOM | `difficulty_class.html:35-59`, `difficulty_dashboard.html:41-65` |
| `x-cloak` (anti-FOUC) | usage répandu (panels, dropdowns) |
| Toggle natif (switch) | `observation_form.html:139-143` |

Particularité : `difficulty_*` manipulent le DOM **impérativement** via `classList`/`textContent` plutôt que par binding Alpine déclaratif — anti-pattern Alpine.

---

## 10. Incohérences (constat + fichier:ligne + sévérité)

| # | Constat | Réf | Sévérité |
|---|---|---|---|
| 1 | **Double breakpoint de bascule** : `base.html` commute sur `lg` (1024) mais la saisie de notes sur `sm` (640). Entre 640–1024px : tableau desktop de notes + bottom-nav mobile + pas de sidebar (UX hybride non maîtrisée sur tablette). | `notes_class.html:171,200` vs `base.html:647,751` | **Majeur** |
| 2 | **Titre de page absent en mobile enseignant** : le header mobile enseignant (`base.html:583-643`) n'affiche pas `{% block page_title %}` ; le bloc titre est `hidden lg:flex`. Les pages dont l'identité repose sur `page_title` (notes_dashboard, observations, notifications…) n'ont **aucun titre visible** en mobile. | `base.html:647-657` | **Majeur** |
| 3 | **Logique de bouton « enregistrer » dupliquée** mobile/desktop (même libellé, même handler, 2 markups) — risque de divergence à la maintenance. | `attendance_class.html:198-234` | Mineur |
| 4 | **`handleScoreUpdate` copié-collé à l'identique** dans 2 fichiers (>20 lignes JS). | `difficulty_class.html:35-57` ≡ `difficulty_dashboard.html:41-63` | Majeur |
| 5 | **3 implémentations d'onglets** différentes (Alpine+HTMX / liens reload / Alpine client) pour un composant visuellement identique. | `notes_class.html:203` / `notes_dashboard.html:87` / `observations.html:56` | Mineur |
| 6 | **Mix icônes Lucide + SVG inline** : notes/ utilise des SVG bruts (recherche, flèches, spinner) alors que tout le reste est Lucide. | `notes_table.html:103-105,227`, `note_cell.html:77-80` vs reste | Mineur |
| 7 | **Sous-utilisation des utilitaires partagés** `.card`/`.btn-primary`/`.input-field` : la majorité des écrans enseignant (dashboard, attendance, difficulty, observations) réécrivent les styles à la main, divergeant de notes_dashboard qui les utilise. | `dashboard.html` (0 util) vs `notes_dashboard.html:22,38,53` | Majeur |
| 8 | **Rayons de carte incohérents** : `rounded-2xl` vs `rounded-xl` vs `.card` au sein du même portail. | `dashboard.html:47` vs `difficulty_student_card.html:5` | Mineur |
| 9 | **Cibles tactiles < 44px** : boutons ▲▼ `w-7 h-6` (24px h), chips de filtre `py-1.5`, toggle leçons. | `unit_lessons_edit.html:10-15` | Mineur |
| 10 | **Manipulation DOM impérative** dans difficulty (classList/textContent) au lieu de bindings Alpine — contourne le modèle réactif. | `difficulty_class.html:42-56` | Mineur |
| 11 | **`top` sticky en dur non aligné aux breakpoints** : `sticky top-14 sm:top-16` (attendance) et `top-14 lg:top-16` (notifications) supposent une hauteur de header fixe qui diverge du `min-h-[56px] sm:min-h-[64px]` réel. | `attendance_class.html:116`, `notifications.html:55` | Mineur |
| 12 | **Validation de note divergente** : client (mobile, `0–max`) vs serveur (desktop) — règles potentiellement désynchronisées. | `notes_class.html:66-68` vs `note_cell.html` (serveur) | Majeur |

Aucun bloquant identifié dans le périmètre.

---

## 11. Synthèse rapide

- Portail **résolument mobile-first** : la plupart des écrans enseignant sont conçus en `max-w-2xl mx-auto` mono-colonne, simplement centrés sur desktop ; le desktop riche (sidebar, tableaux) n'existe vraiment que pour notes et difficulté.
- La **saisie de notes** est le sommet de complexité responsive (2 UX complètes, bascule à `sm`).
- HTMX très présent côté unités (polling + édition inline) et notes (édition cellule) ; ailleurs surtout `swap=none` + événements.
- Dette principale : duplication de logique (boutons, JS difficulté), double système de breakpoints, sous-utilisation des utilitaires CSS partagés.
