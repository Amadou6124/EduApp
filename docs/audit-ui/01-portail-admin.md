# Audit UI/UX — Portail Direction / Admin (gestion + finance)

> Audit **en lecture seule** de l'existant. Aucun fichier d'application modifié.
> Périmètre : `templates/{dashboard,schools,students,accounting,finance,payments,bulletins,settings,superadmin,promoter,team}/`, `accounts/{login,select_school,portal_coming_soon}.html`, pages d'erreur (`400/403/404/500.html`).
> `notes/` (portail enseignant) exclu. `base.html` n'est décrit que sous l'angle « comment l'admin l'utilise » (analyse profonde faite ailleurs).
> Date : 2026-06-28. Source de vérité CSS : `static/css/output.css` (compilé depuis `static/css/input.css` + `tailwind.config.js`).

## 0. Chiffres clés

| Mesure | Valeur |
|---|---|
| Fichiers HTML dans le périmètre | **132** |
| Pages « plein écran » (extends) | 24 → `base.html`, 11 → `superadmin/base_superadmin.html`, 9 → `settings/settings_base.html` |
| Templates autonomes (`<!DOCTYPE>` propre, n'étendent rien) | 7 : `base_superadmin.html`, `login.html`, `select_school.html`, `portal_coming_soon.html`, 3 PDF, (+ `500.html`) |
| PDF (impression) | 3 : `accounting/pdf/payslip.html`, `payments/pdf/receipt_standard.html`, `bulletins/pdf/bulletin_template.html` |
| Icônes Lucide (`data-lucide`) | **336** occurrences |
| Préfixes responsive | `sm:` **143**, `lg:` **38**, `md:` **9**, `xl:` **2** |
| Attributs HTMX | `hx-target` 101, `hx-swap` 100, `hx-post` 66, `hx-get` 45, `hx-indicator` 13, `hx-trigger` 12, `hx-vals` 8, `hx-on` 5, `hx-confirm` 2, `hx-push-url` 2, `hx-delete` 0 |
| Attributs Alpine | `@click` 182, `x-show` 104, `:class` 83, `x-cloak` 65, `x-data` 60, `x-text` 53, `$store` 39, `x-model` 21, `x-for` 8, `x-init` 8, `x-effect` 1 |
| Classes composant `.btn-*` (fichiers) | 51 |
| Classes `.card` / `.kpi` / `.input-field` (occurrences) | 87 / 45 / 51 |
| États vides (`Aucun(e)`) | 73 |

---

## 1. Arborescence des templates (page → extends → includes)

### 1.1 Pages étendant `base.html`

| Page | Includes principaux |
|---|---|
| `dashboard/dashboard.html` | `dashboard/partials/{kpi_cards,alerts,class_health,activity_feed}.html` |
| `schools/class_list.html` | `class_stats`, `class_table_body`, `class_form_fields`, `includes/search_bar.html` |
| `schools/announcements/list.html` | `announcements/partials/announcement_card.html` |
| `students/student_list.html` | `student_stats`, `student_table_body`, `includes/search_bar.html` |
| `students/student_detail.html` | `student_profile_view`, `finance/partials/timeline.html`, `guardian_section`, `guardian_form`, `obs_card` |
| `students/tracking.html` | `tracking_{absences,difficulty,observations}.html` |
| `payments/dashboard.html` | `payment_stats`, `payment_list_body.html` |
| `accounting/dashboard.html` | — (Chart.js inline) |
| `accounting/bilan_dashboard.html` / `salary_dashboard.html` / `expense_dashboard.html` / `emargement.html` / `staff_list.html` | `salary_row`, `expense_list`, `employee_remuneration`, `substitute_results` |
| `bulletins/bulletins_main.html` | `_bulletins_badge`, `bulletins_tab`, `rankings_tab`, `health_tab` |
| `team/team_list.html` / `team_detail.html` | `member_card`, `member_card_deactivated`, `member_search_result`, `team_edit_form`, `staff_permissions`, `teacher_subjects` |
| `promoter/{synthese,ecoles,finances,school_detail}.html` | partials propres |
| `400/403/404.html` | — (contenu inline) |

### 1.2 Pages étendant `settings/settings_base.html` (qui étend `base.html`)

`general`, `appearance`, `subjects`, `school_years`, `school_year_periods`, `bulletin`, `receipt`, `fees`, `coming_soon`. Chacune ne fait que poser un `<h2>`/sous-titre puis `{% include %}` son `*_form.html` ou ses partials de liste.

### 1.3 Pages étendant `superadmin/base_superadmin.html` (document HTML autonome — voir §2.3)

`dashboard`, `school_list`, `school_create`, `school_update`, `director_create`, `director_update`, `user_list`, `user_create`, `group_list`, `group_create`, `ia_dashboard`.

### 1.4 Templates autonomes (hors hiérarchie `base.html`)

`accounts/login.html`, `accounts/select_school.html`, `accounts/portal_coming_soon.html`, `500.html`, les 3 PDF. Ils ré-déclarent `<!DOCTYPE>` + leur propre `<head>`/CSS.

---

## 2. Headers (desktop ET mobile)

### 2.1 Header standard (via `base.html`, rôle director/staff)

Header `sticky top-0 z-20` sur `bg-white border-b`. Trois zones distinctes pilotées par classes responsive (`base.html:579-726`) :

- **Header MOBILE non-teacher** (`flex` ... `lg:flex-row`, ligne 647-725) : sur 2 lignes.
  - Ligne 1 : titre `<h1>` (`text-lg`, `truncate`) + à droite 3 actions tactiles 44×44 : recherche (`@click="$store.search.open=true"`), cloche (sans badge, sans `href` — bouton inerte, `base.html:666`), avatar (`@click="$store.accountSheet.open=true"`).
  - Ligne 2 (`lg:hidden`, ligne 712-724) : école (cliquable si multi-école) · année · période, en `text-xs`.
- **Header DESKTOP** (`lg:flex`) :
  - Gauche : `{% block breadcrumb %}` (utilisé seulement par `promoter/school_detail.html`) + `<h1>` `lg:text-2xl` + `{% block page_subtitle %}`.
  - Droite (`hidden lg:flex`, ligne 680-709) : `{% block header_actions %}` (utilisé par `student_detail`, `team_detail` uniquement) + badge année (lien vers `settings:school-years`) + cloche bouton inerte.

Le sous-titre n'apparaît qu'en desktop (`hidden lg:block`, ligne 656).

### 2.2 Header mobile « enseignant »

Bloc distinct `flex lg:hidden` (ligne 582-644) : avatar→paramètres, nom d'école central, cloche **fonctionnelle** avec badge `teacher_unread_count`. Hors périmètre admin mais présent dans le même header.

### 2.3 Header superadmin (totalement séparé)

`superadmin/base_superadmin.html` est un **document HTML complet indépendant** (pas d'extends, pas d'Alpine ni HTMX chargés, son propre `lucide.createIcons()`). Top-navbar fixe `h-[52px] bg-primary-900` avec pastille « SUPERADMIN » ambre, nom utilisateur, lien « Retour app ». Pas de recherche globale, pas de notifications, pas de bottom-sheet — UX nettement plus pauvre que le portail principal.

### 2.4 Headers des pages autonomes

`login`/`select_school`/`portal_coming_soon` n'ont pas de header applicatif (carte centrée). `400/403/404` héritent du header `base.html` (donc sidebar + header complets sur une page d'erreur) ; `500.html` est autonome.

---

## 3. Footers

- **Pas de footer applicatif desktop** dans `base.html`. Le seul « footer » est la **bottom-bar mobile** (§4.3).
- **Footer mobile** : nav fixe `lg:hidden fixed bottom-0` (`base.html:751`), `rounded-t-2xl`, ombre haute, `min-h-[68px]`, respecte `env(safe-area-inset-bottom)`.
- `payments/dashboard.html` ajoute une **barre de pied contextuelle** (`#receipt-footer-bar`, ligne 177) qui s'aligne dynamiquement sur la largeur de la sidebar (`:class="$store.sidebar.open ? 'lg:left-64' : 'lg:left-16'"`).
- `login.html` : micro-footer texte « Contactez votre administrateur ».
- Superadmin : aucun footer.

---

## 4. Navigation

### 4.1 Sidebar desktop (`base.html:37-570`)

`<aside hidden lg:flex>` largeur pilotée par store : `w-64` (ouvert) / `w-16` (réduit), persistée en `localStorage('sidebar-open')`. Items director/staff (lignes 210-379), conditionnés par rôle + permissions + `request.school.accounting_enabled` :
Dashboard · Classes · Élèves · **Suivi élèves** (badge `unread_observations_count`) · Paiements · Notes · Bulletins · Annonces · Équipe · Comptabilité · Émargement · Paie mensuelle · Dépenses · Bilan financier · (Superadmin en `text-amber-600`).
Item actif : `bg-primary-50 text-primary-700 font-semibold` (détection via `request.resolver_match.app_name`/`url_name`). Bas de sidebar : menu utilisateur (avatar + dropdown remontant) avec switch d'école, Paramètres, Langue (FR actif, EN/AR « Bientôt »), aide, mentions, déconnexion.

### 4.2 Sidebar settings (`settings/settings_base.html`)

`settings_base` **neutralise** `{% block sidebar %}` et `{% block sidebar_margin %}` (lignes 3-4) → la sidebar principale disparaît, remplacée par une sous-sidebar `w-56` desktop (`hidden sm:block`) groupée en 3 sections **École / Pédagogie / Finance**. Construite par **7 inclusions** de `settings/partials/nav_item.html` (lignes 41,42,48,49,50,56,57). En mobile (`sm:hidden`), la nav devient un `<select onchange>` avec `<optgroup>` (lignes 67-83) — pattern différent du reste de l'app.

`nav_item.html` : `<a>` actif `bg-primary-50 text-primary-700` ou `<span>` grisé + badge « Bientôt » si `available=False`.

### 4.3 Nav mobile (bottom-bar, `base.html:751-920`)

Director/staff : Accueil · Élèves (badge observations) · Paiements · Notes · **Plus** (ouvre `$store.moreSheet`). Indicateur actif = point `bg-primary-600` au-dessus de l'icône. Variantes distinctes pour teacher / promoter / parent.

### 4.4 Bottom-sheets mobiles (`base.html`)

Trois sheets remontés hors du bloc content (survivent aux swaps HTMX) :
- `moreSheet` (director/staff, ligne 998) : sections **Gestion / Finances / Administration** + pied compte/déconnexion. Items en `.sheet-item`.
- `accountSheet` (ligne 1095) : identité + switch école + déconnexion.
- `teacherMoreSheet` (ligne 924) : équivalent enseignant.

### 4.5 Fil d'Ariane et onglets internes

- Breadcrumb : `{% block breadcrumb %}` quasi inutilisé (1 page). Quelques pages réinventent un lien « retour » maison (ex. `settings/settings_base.html:29`, `school_year_periods.html:9`, `base_superadmin.html:20`).
- **Onglets-pills internes** (pattern récurrent `bg-gray-100 rounded-lg p-1 flex gap-1`) :
  - `students/student_list.html:173` — filtres via liens `?filter=` (rechargement page).
  - `payments/dashboard.html:85` — onglets via `hx-get` + `hx-push-url`.
  - `bulletins/bulletins_main.html:138` — onglets via Alpine `x-data{tab}` + `hx-get` vers `#tab-content`.
  → 3 implémentations différentes du même visuel d'onglets.

### 4.6 Navigation superadmin

Sidebar `w-56` propre (4 items : Vue d'ensemble, Écoles, Utilisateurs, Groupes) + CTA « Nouvelle école » en bas + bottom-nav mobile à 4 items. Pas de « Plus », pas de sheets.

---

## 5. Liste exhaustive des écrans

| Domaine | Écran | Rôle |
|---|---|---|
| Dashboard | `dashboard.html` | KPIs, alertes, 2 graphiques Chart.js, santé classes, activité, actions rapides, FAB mobile |
| Schools | `class_list.html` | Liste/cartes classes, stats, import Excel, modales création/édition |
| | `announcements/list.html` | Annonces (cartes) |
| Students | `student_list.html` | Liste/cartes élèves, filtres, inscription (panneau latéral riche Alpine), import |
| | `student_detail.html` | Fiche élève : profil, timeline financière, tuteurs, observations |
| | `tracking.html` | Suivi (absences / difficultés / observations) |
| Payments | `dashboard.html` | Stats, recherche/filtre HTMX, onglets statut, panneaux encaissement + reçu |
| Accounting | `dashboard.html` | 4 KPI animés, alertes, graphe 6 mois, accès rapides, dépenses récentes |
| | `bilan_dashboard` / `salary_dashboard` / `expense_dashboard` / `emargement` / `staff_list` | Bilan, paie, dépenses, émargement du jour, rémunération équipe |
| Finance | partials `allocation_preview`, `collect_panel`, `timeline` | Briques réutilisées par payments/students |
| Bulletins | `bulletins_main` (3 onglets), `bulletin_preview` | Génération/consultation bulletins |
| Settings | `general`, `appearance`, `subjects`, `school_years`, `school_year_periods`, `bulletin`, `receipt`, `fees`, `coming_soon` | Voir §6 |
| Superadmin | `dashboard`, `school_*`, `director_*`, `user_*`, `group_*`, `ia_dashboard` | Administration plateforme |
| Promoter | `synthese`, `ecoles`, `finances`, `school_detail` | Vue multi-écoles |
| Team | `team_list`, `team_detail` | Personnel/staff |
| Accounts | `login`, `select_school`, `portal_coming_soon` | Auth |
| Erreurs | `400/403/404/500` | Pages d'erreur |
| PDF | `payslip`, `receipt_standard`, `bulletin_template` | Documents imprimables |

---

## 6. Settings — détail par écran

| Écran | Rendu | Interactions |
|---|---|---|
| `general` | Form classique (`general_form.html`) | POST |
| `appearance` | Form (`appearance_form.html`) — logo/couleurs reçus & bulletins | POST |
| `subjects` | 2 colonnes ; gauche : create Alpine collapsible + suggestions « chips » + liste HTMX ; droite : `<select hx-get>` → `#class-subjects-panel` | HTMX `change` |
| `school_years` | En-tête + form collapsible Alpine (`x-data{showForm}`) + liste HTMX | HTMX + event `school-year-saved` |
| `school_year_periods` | Templates rapides « 3 Trimestres / 2 Semestres » via `$store.confirm` + `htmx.ajax`, form manuel collapsible, liste périodes | `$store.confirm` + HTMX OOB |
| `bulletin` | Form (`bulletin_form.html`) | POST |
| `receipt` | `receipt_content.html` (standard vs custom flow + preview) | HTMX |
| `fees` | 2 sections : catalogue de cartes (`fee_catalog` → `fee_card`) + gabarit de tranches ; **modal** ajout/édition Alpine, corps chargé en HTMX ; montants éditables inline auto-save (`fee_card.html:42`) | HTMX inline + modal |
| `coming_soon` | État vide illustré (icône SVG choisie par `section_icon`) + badge « Disponible prochainement » + skeleton décoratif | statique |

Pattern dominant des settings : **form/liste partielle rechargée en HTMX**, formulaires de création **collapsibles via Alpine** (`x-data{showForm}` + transition), confirmations destructives via `$store.confirm` global. Cohérent et bien rôdé sur ce module.

---

## 7. Structure de contenu des pages clés

- **Dashboard** : salutation → `kpi_cards` → `alerts` → grille 2 graphiques (`lg:grid-cols-2`) → `class_health` → `activity_feed` → actions rapides (grille `grid-cols-2 md:grid-cols-4`) → FAB mobile. Bonne hiérarchie verticale, sections numérotées en commentaires.
- **student_list** : barre d'actions → `student_stats` → recherche + switch cards/table → onglets filtre → liste → panneau latéral d'inscription (Alpine ~200 lignes : calculs frais/tranches live, récap « à la rentrée ») → modal import. Logique métier très dense côté client.
- **payments dashboard** : zone HTMX invisible de rafraîchissement (`payment-collected from:body`) → stats → form recherche/filtre HTMX → onglets statut → liste → 3 panneaux superposés (encaissement `z-50`, historique modal, reçu `z-[70]`) + footer reçu contextuel `z-[80]`. Empilement de z-index élevé.
- **accounting dashboard** : 4 KPI (compteurs animés `requestAnimationFrame`) → alertes → graphe combo bar+line → accès rapides (3 cartes) → dépenses récentes. Le KPI « Résultat net » s'écarte du composant `.kpi` (carte verte/rouge conditionnelle).

---

## 8. Responsive

Breakpoint **dominant `sm:` (640px, 143 occ.)** = bascule mobile↔desktop principale (ex. cards-only < sm, switch cards/table caché en `hidden sm:flex`). `lg:` (1024px, 38 occ.) = bascule sidebar/header/bottom-bar dans `base.html`. `md:`/`xl:` quasi inexistants (9/2) → **approche essentiellement bi-breakpoint**.

Différences mobile/desktop notables : sidebar→bottom-bar+sheets ; header 1 ligne desktop → 2 lignes mobile ; settings sidebar→`<select>` ; modales `items-end sm:items-center` (sheet en bas sur mobile, centrée desktop) ; vues élèves/classes/paiements forcées en `cards` sous 640px (`window.innerWidth < 640`). Cibles tactiles `min-h-[44px]` / `min-w-[44px]` largement appliquées (bonne pratique mobile).

---

## 9. Composants — inventaire et cohérence

> ⚠️ Source de vérité = `static/css/input.css` (compilé dans `output.css`). `static/css/components.css` **n'est référencé nulle part** (mort, voir §11-B1) et définit des `.btn-*`/`.badge-*` CONTRADICTOIRES (token `brand-blue`, pas de `.btn` base).

| Composant | Classe(s) canonique(s) | Variantes / dérives observées | Cohérence |
|---|---|---|---|
| **Boutons** | `.btn-primary/-secondary/-danger/-ghost/-gold` (`input.css:28-67`) | 51 fichiers utilisent les classes. MAIS nombreux boutons **inline** réinventés (≥15 fichiers, ex. `settings/subjects.html:27` `bg-primary-600 text-white text-xs`, `class_list.html:30` bouton outline maison, `school_year_periods.html:29` outline maison, superadmin `*_create.html`). Spinner d'envoi : tantôt SVG inline, tantôt `htmx-indicator`. | **Moyen** — base solide mais beaucoup d'exceptions inline |
| **Inputs** | `.input-field` (51 occ.) | Concurrencé par des `<input>`/`<select>` stylés à la main (`payments` filtres OK en `.input-field` ; mais `settings/subjects.html:82-87`, `team_list.html:151/206`, `login.html:132` redéfinissent border/focus en dur) | **Moyen** |
| **Cards** | `.card` (87 occ.) + `.card-header/body/footer` | Souvent `card p-5`/`card p-6`/`card p-4` (padding non standardisé) ; KPI custom accounting hors `.card` | Bon (classe) / padding hétérogène |
| **KPI** | `.kpi`, `.kpi-icon`, `.kpi-value`, `.kpi-label` (45 occ.) | accounting `dashboard.html` n'utilise PAS `.kpi` (cartes maison animées) | Moyen |
| **Tables** | `.table-card` (10), `.data-table` (4) | `.data-table` très peu adopté ; la plupart des listes sont des **grilles de cartes** ou des tables ad-hoc dans les `*_table_body.html` | Faible adoption du composant table |
| **Badges** | `.badge-*` (success/warning/danger/info/primary/neutral/purple/emerald) | Bien utilisés (`fee_card.html:25,39`) mais aussi badges inline (`<span class="...rounded-full px-2 py-0.5...">` réécrits, ex. `team_list.html:133`, et **hex codés en dur** `#F3F0FE/#5B21B6` `team_list.html:188,223`) | Moyen |
| **Modales** | Pattern Alpine répété (overlay `bg-black/40 backdrop-blur-sm` + panneau `rounded-2xl`/`rounded-t-2xl sm:rounded-2xl`, transitions identiques) | Aucune abstraction → **dupliqué** dans `class_list` (3 modales), `student_list` (import), `fees`, `team_list` (pwd modal), payments (history)… | Visuellement cohérent / structurellement dupliqué |
| **Panneaux latéraux (drawers)** | `fixed top-0 right-0 ... animate-slide-in-right` / translate-x | Répété : students, payments (×3), team (×2). Largeurs variables `sm:w-[480px]/[520px]/[540px]/[680px]` | Cohérent visuellement, largeurs ad-hoc |
| **Toasts** | `.toast`, `.toast-stack` + `settings/partials/toast.html` (Alpine global, inclus dans `base.html:1265`) | Source unique, bien centralisé | **Bon** |
| **Dropdowns** | Menu utilisateur sidebar + menus école mobile (Alpine `@click.away`) | Positionnement via `getBoundingClientRect` JS inline (fragile) | Moyen |
| **Onglets** | pills `bg-gray-100 rounded-lg p-1` | 3 implémentations (liens / HTMX / Alpine) — voir §4.5 | Faible (cohérence comportementale) |
| **Pagination** | — | Aucun composant de pagination repéré dans le périmètre (listes non paginées côté template) | n/a |
| **États vides** | `Aucun(e)` ×73, motif récurrent « icône ronde + titre + sous-texte + CTA » | Réécrit à chaque fois (pas de partial commun) ; `coming_soon.html` a son propre style | Visuellement cohérent / dupliqué |
| **Modal de confirmation** | `$store.confirm` global (`base.html:1268-1368`) | Très bien utilisé (fees, periods, team) au lieu de `confirm()` natif | **Bon** |

---

## 10. Patterns HTMX & Alpine récurrents

**HTMX** (cœur de l'interactivité admin) :
- Liste rechargée en place : `hx-get` form filtre → `hx-target="#payment-list-area" hx-swap="outerHTML"` (`payments/dashboard.html:45-50`).
- Rafraîchissement piloté par événement serveur : `hx-trigger="payment-collected from:body"` (`payments/dashboard.html:33-37`), `team-member-added`, `school-year-saved`.
- Édition inline auto-save : `hx-post ... hx-trigger="change" hx-swap="none"` (`fee_card.html:42-47`).
- Chargement paresseux d'onglet : `hx-trigger="load"` (`bulletins_main.html:188`).
- Modale/panneau dont le **corps** est injecté par HTMX (`#fee-modal-body`, `#collect-panel-body`, `#edit-panel-body`).
- Upload : `hx-encoding="multipart/form-data"` + `hx-indicator` (imports élèves/classes).
- `htmx.ajax(...)` appelé depuis Alpine (`$store.confirm.onConfirm`, `team_list.openEditPanel`).

**Alpine** :
- `x-data` de page sous forme de **fonction JS** (`studentsPageData()`, `paymentsPageData()`, `teamPageData()`) déclarée dans `{% block extra_head %}` — pattern propre et récurrent.
- `x-show` + transitions pour modales/panneaux/sections collapsibles ; `x-cloak` systématique (65 occ.).
- Stores globaux (`base.html`) : `sidebar`, `search`, `moreSheet`, `accountSheet`, `teacherMoreSheet`, `confirm`, + `payments` (par page).
- Toggles « iOS » faits main : `<input class="sr-only peer">` + `peer-checked` (student_list ×3, fee_card).
- Filtrage client par `x-show` sur `dataset` (`team_list.html:158`).
- Compteurs animés via `requestAnimationFrame` dans `x-data.init()` (`accounting/dashboard.html:26`).
- Persistance `localStorage` pour préférences de vue (cards/table).

---

## 11. Incohérences repérées (constat, fichier:ligne, sévérité)

| # | Sévérité | Constat |
|---|---|---|
| **B1** | **Majeur** | **`static/css/components.css` est mort** : référencé nulle part (seul `output.css` est chargé, `base.html:13`) et **contredit** `input.css` — il définit `.btn-primary` sur le token `brand-blue` sans base `.btn`, badges sur `padding`/couleurs différents. Risque de confusion forte pour tout dev qui l'éditerait en croyant agir sur l'UI. |
| **B2** | **Majeur** | **CDN externes dans `accounts/login.html`** : Manrope via `fonts.googleapis.com` (`login.html:9-11`) et **Alpine via `cdn.jsdelivr.net`** (`login.html:16`), alors que tout le reste est vendored (`base.html`). Même dépendance CDN dans `select_school.html` et `portal_coming_soon.html`. → incohérence d'architecture + dépendance réseau sur l'écran de connexion. |
| **B3** | Majeur | **Header « Notifications » non fonctionnel** : la cloche director/staff est un `<button>` inerte sans action, mobile (`base.html:666`) et desktop (`base.html:704`). Affordance trompeuse. |
| **B4** | Majeur | **Superadmin = portail à part entière divergent** : `base_superadmin.html` ne charge ni Alpine ni HTMX, pas de recherche, pas de sheets, navbar `bg-primary-900` propre. Double système de mise en page à maintenir. |
| **M1** | Mineur | **Dérive de couleur `indigo-*`** au lieu du token `primary-*` : `400.html`, `403.html`, `404.html` (titres + boutons `bg-indigo-600`), et `schools/announcements/partials/announcement_card.html`. |
| **M2** | Mineur | **Couleurs hex codées en dur** (9 fichiers) : `team_list.html:188,223` (`#F3F0FE`, `#5B21B6`) au lieu d'une classe `badge-purple`/`bg-purple-50`. |
| **M3** | Mineur | **Boutons/inputs inline réinventés** dans ≥15 fichiers malgré l'existence de `.btn-*`/`.input-field` (voir §9) — incohérences de padding/focus/spinner. |
| **M4** | Mineur | **Onglets internes : 3 implémentations** du même visuel (liens vs HTMX vs Alpine) — `student_list:173`, `payments:85`, `bulletins_main:138`. |
| **M5** | Mineur | **Mix icônes Lucide + SVG inline** : beaucoup d'écrans (`subjects.html`, `school_years.html`, `class_list.html`, `coming_soon.html`, `login.html`, toasts) utilisent des `<svg>` Heroicons en dur au lieu de `data-lucide`, alors que Lucide est le standard (336 occ.). |
| **M6** | Mineur | **`.data-table` quasi inutilisé** (4 occ.) : la plupart des listes contournent le composant table prévu (grilles de cartes / tables ad-hoc). |
| **M7** | Mineur | **Modales/drawers dupliqués** sans partial commun (≈10 instances), largeurs de drawer ad-hoc (`sm:w-[480px]`…`[680px]`). |
| **M8** | Mineur | **Pages d'erreur 400/403/404 héritent de `base.html`** → affichent sidebar + header complets (avec navigation) sur une page d'erreur, tandis que `500.html` est autonome → traitement incohérent des erreurs. |
| **M9** | Mineur | **États vides non factorisés** (motif identique répété ~73 fois) ; padding `.card` non standardisé (`p-4/p-5/p-6`). |

---

*Fin de l'audit — aucun fichier d'application modifié.*
