# Audit UI/UX — Design system de facto (transversal aux 4 portails)

> Audit **en lecture seule**. Aucun fichier source n'a été modifié.
> Périmètre : 181 templates `.html`, `tailwind.config.js`, `static/css/{input,components,student,output}.css`, les 5 bases.
> Stack : Tailwind CSS (build local `output.css`), Alpine.js, HTMX, Chart.js, Lucide, police Manrope. Tout vendored dans `static/vendor/`.

---

## 0. Verdict express

Il existe un **design system partiel, déclaré mais sous-appliqué**. Les tokens (couleurs, typo, ombres) sont définis proprement dans `tailwind.config.js`, et une bibliothèque de composants `@apply` existe dans `input.css`. Mais l'usage réel est massivement **inline/utilitaire** : les composants `@apply` sont court-circuités par des signatures répétées à la main dans les templates (ex : `btn-primary` est utilisé dans 47 fichiers, mais `bg-primary-600` inline apparaît 131 fois). Le portail élève (`/learn/`) et, dans une moindre mesure, le portail parent **divergent** (couleur, CDN font, palette hardcodée). Un fichier CSS entier (`components.css`) est **mort** (token inexistant, non linké).

---

## 1. COULEURS

### 1.1 Tokens définis (`tailwind.config.js:35-84`)

| Token | Type | Valeur clé | Portée déclarée |
|---|---|---|---|
| `primary.50→950` | échelle Indigo (11 nuances) | `600 = #4F46E5` | Admin · Directeur · Prof · Parent · Promoteur · Superadmin |
| `student.50→950` | échelle Emerald (11 nuances) | `500 = #10B981` | `/learn/` exclusivement |
| `gold.DEFAULT/50/100/400/500/600` | accent Or (6 nuances) | `500 = #F59E0B` | XP / badges (partagé) |
| `success` | sémantique | `#10B981` | global |
| `warning` | sémantique | `#F59E0B` | global |
| `danger` | sémantique | `#EF4444` | global |
| `info` | sémantique | `#6366F1` | global |

Un système sémantique existe (`success`/`warning`/`danger`/`info`) **mais il est très peu employé** : les templates utilisent presque toujours les palettes Tailwind brutes (`green-`, `red-`, `amber-`) au lieu des alias sémantiques.

### 1.2 Couleurs hardcodées dans les templates

- **78 hex distincts** dans `templates/` (`grep '#[0-9a-fA-F]{3,6}'`), répartis sur **46 fichiers**.
- **496 attributs `style="..."`** inline.
- rgba : ~50 valeurs distinctes, dominées par des `rgba(255,255,255,.0x)` (overlays sombres du portail élève) et `rgba(0,0,0,0.05)`.

**Doublons / quasi-doublons notables :**

| Cas | Hex hardcodé | Token équivalent | Sévérité |
|---|---|---|---|
| Indigo 600 dupliqué | `#4F46E5` (13×) | `primary-600` | majeur |
| Indigo accent | `#6366F1` (2×) | `primary-500` / `info` | mineur |
| Indigo hover | `#4338CA` (3×) | `primary-700` | mineur |
| Danger | `#EF4444` (21×) + `#ef4444` (2×) + `#F87171`/`#FB7185` | `danger` / `red-*` | majeur (casse + variantes) |
| Success | `#22C55E`/`#22c55e` (24×), `#16A34A`, `#10B981`, `#34D399` | `success` / `student-*` | majeur |
| Blanc | `#fff` (51×), `#ffffff` (8×) | inutile (bg-white) | mineur |
| Noir | `#000` (27×) | inutile | mineur |
| Or | `#F59E0B`/`#f59e0b` (10×), `#FBBF24` (9×), `#D97706` | `gold-*` | majeur |
| Violets élève | `#6d28d9`, `#5B21B6`, `#6D28D9`, `#A78BFA`, `#A855F7` | aucun token | majeur (hors palette) |
| Fonds sombres élève | `#0b0b1a`, `#07060f`, `#09090E`, `#1a1340`, `#262638`… (~15 variantes near-black) | aucun token | majeur |
| Confettis JS | `#FFD700,#FF6B6B,#4ECDC4,#45B7D1,#96CEB4,#FFEAA7` | aucun token | mineur (`base_student.html:116`) |

**Constat couleur :** la palette **fonctionne en intention** mais la dette hardcodée est concentrée dans (a) le portail élève (violets + near-blacks totalement hors système) et (b) la duplication systématique des hex indigo/success/danger qui ont pourtant un token.

### 1.3 Couleurs Tailwind brutes les plus employées (classes `bg-/text-/border-`)

| Famille | Occurrences | Statut |
|---|---|---|
| `gray-*` | 3058 | neutre, cohérent |
| `red-*` | 508 | devrait passer par `danger` |
| `green-*` | 348 | devrait passer par `success`/`student` |
| `amber-*` | 254 | devrait passer par `warning`/`gold` |
| `orange-*` | 82 | hors système |
| `blue-*` | 53 | **collision** avec `primary` (indigo) — incohérence visuelle |
| `yellow-*` | 39 | doublon `amber` |
| `indigo-*` | 23 | doublon `primary` |
| `purple/violet-*` | 31 | hors système (élève) |

Incohérence transversale **majeure** : coexistence de `blue-*`, `indigo-*` et `primary-*` (indigo) pour exprimer la même couleur de marque.

---

## 2. TYPOGRAPHIE

### 2.1 Famille
- Token unique : `font-sans = ['Manrope', 'system-ui', 'sans-serif']` (`tailwind.config.js:16`).
- **Divergence de chargement** : `base.html`/`base_parent.html`/`base_superadmin.html` chargent Manrope **self-hosté** (`vendor/fonts/manrope/manrope.css`). `base_student.html:8-10` charge Manrope via **Google Fonts CDN** (`fonts.googleapis.com`) — incohérence d'hébergement + dépendance réseau externe (sévérité majeure offline).
- `font-mono` : 18×, `font-serif` : 1× (`bulletins`), `font-sans` explicite : 3×.

### 2.2 Échelle de tailles (`tailwind.config.js:21-30`)
8 paliers custom : `2xs`(11) `xs`(12) `sm`(14) `base`(16) `lg`(18) `xl`(20) `2xl`(24) `3xl`(30) — line-height + letter-spacing définis par palier. Hiérarchie h1-h3/p appliquée globalement via `@layer base` (`input.css:15-18`).

**Tailles réellement utilisées dans les templates :**

| Classe | Occurrences |
|---|---|
| `text-xs` | 861 |
| `text-sm` | 827 |
| `text-2xl` | 77 |
| `text-base` | 67 |
| `text-xl` | 59 |
| `text-lg` | 53 |
| `text-3xl` | 13 |
| `text-4xl` / `text-5xl` | 2 / 2 (hors échelle config) |
| **`text-[10px]`** | **160** (arbitraire) |
| **`text-[11px]`** | **59** (= `2xs`, mais contourné) |
| **`text-[9px]`** | **9** (arbitraire, < échelle) |

**Constat :** échelle cohérente sur le papier, mais **228 tailles arbitraires `text-[..px]`** la court-circuitent — notamment `text-[10px]` (badges/labels micro) qui n'a aucun token et `text-[11px]` qui duplique `2xs`.

### 2.3 Poids
6 poids réellement utilisés : `font-semibold` (687), `font-medium` (462), `font-bold` (299), `font-normal` (39), `font-extrabold` (35), `font-black` (8), `font-light` (2). Cohérent dans l'ensemble ; `extrabold`/`black` concentrés sur portails parent/élève (titres marketing).

---

## 3. ESPACEMENT

Grille 4px déclarée en commentaire config (`tailwind.config.js:120`), pas de surcharge `spacing` → défauts Tailwind.

**Valeurs les plus fréquentes :**

| `gap-*` | n | `p-*` | n |
|---|---|---|---|
| gap-2 | 295 | p-4 | 147 |
| gap-3 | 284 | p-5 | 58 |
| gap-1 | 203 | p-1 | 57 |
| gap-4 | 57 | p-6 | 51 |
| | | p-3 | 50 |
| | | p-2 | 48 |

**Espacement arbitraire en px (`p-/m-/gap-[..px]`) : 0 occurrence** → l'arbitraire se concentre sur les *dimensions* (`w-/h-/min-h-[..px]`), pas sur le padding/margin. C'est un point **positif** : l'échelle d'espacement est respectée.

Dimensions arbitraires `[..px]` (toutes propriétés confondues) : `[10px]`×160, `[44px]`×60 (cibles tactiles), `[11px]`×59, `[40px]`×12, etc. Les `[44px]`/`[48px]` traduisent une recherche d'accessibilité tactile (positif), mais non tokenisée.

---

## 4. RAYONS / OMBRES / BORDURES

### Rayons (`rounded-*`)
| Classe | n | Rôle déclaré (config:118-120) |
|---|---|---|
| `rounded-full` | 387 | pills/avatars |
| `rounded-lg` | 376 | inputs/btn (8px) |
| `rounded-xl` | 264 | cards (12px) |
| `rounded-2xl` | 176 | modals (16px) |
| `rounded-md` | 36 | hors convention |
| `rounded-3xl` | 4 | hors convention |

Convention documentée et **globalement respectée**. `rounded-md` (36×) est le principal écart mineur.

### Ombres (`shadow-*`) — surchargées en config (`tailwind.config.js:89-93`)
| Classe | n |
|---|---|
| `shadow-sm` | 130 |
| `shadow-2xl` | 32 |
| `shadow-lg` | 17 |
| `shadow-md` | 15 |
| `shadow-xl` | 4 |
| `shadow-[...]` arbitraire | 3 |

Incohérence : la config ne définit que `sm`/`md`/`lg`, mais les templates utilisent `xl`/`2xl` (défauts Tailwind non surchargés) → 36 usages d'ombres hors design system. Ombres arbitraires (`shadow-[0_-4px_12px_...]`) dans les bottom-nav (`base.html:753`, `base_student.html:81`).

### Bordures
Quasi systématiquement `border border-gray-200` / `border-gray-100` (séparateurs). Cohérent.

---

## 5. COMPOSANTS (cœur de l'audit)

**Où vivent les composants ?** Deux sources `@layer components` :
- `input.css` (la **vraie** source, buildée dans `output.css`, linkée partout).
- `components.css` — **FICHIER MORT** : référence le token `bg-brand-blue` qui **n'existe pas** dans `tailwind.config.js` (0 occurrence dans `output.css`), et **aucun template ne le linke**. Il duplique en plus `btn-primary`, `input-field`, `badge-*` avec des signatures **différentes** de `input.css` (ex : `px-4 py-2` vs `px-4 py-2.5`). → Sévérité **majeure** (source de vérité ambiguë / piège pour le futur).

Verdict transversal : **la majorité des styles vivent en utilitaires inline répétés**, pas dans les classes `@apply`.

| Composant | Classe `@apply` (input.css) | Fichiers utilisant la classe | Signatures inline concurrentes | Cohérence |
|---|---|---|---|---|
| **Bouton primaire** | `.btn-primary` (`input.css:37`) | 47 fichiers / 62 refs | `bg-primary-600` inline : **131×** (36 avec rounded) ; `bg-indigo-600` : 3× | **Faible** — la classe existe mais est largement doublée inline |
| Bouton secondaire | `.btn-secondary` (`:43`) | 12 | nombreux `bg-white border border-gray-200/300` inline | Moyenne |
| Bouton danger | `.btn-danger` (`:49`) | 11 | inline `bg-red-600`/`text-red-600` | Moyenne |
| Bouton ghost | `.btn-ghost` (`:55`) | **1** | usage inline `hover:bg-gray-100` partout ailleurs | Quasi inutilisé |
| Bouton gold | `.btn-gold` (`:63`) | **0** | jamais employé | Mort |
| **Input** | `.input-field` (`:70`) | 17 fichiers | beaucoup de `<select>`/`<input>` stylés inline (`settings_base.html:68`) ; aucun input `border-gray` inline détecté en collision directe | Moyenne |
| Form label/helper/error | `.form-label`/`.form-helper`/`.form-error` | **0** chacun | tout inline (`block text-sm font-medium…`) | Définis mais non adoptés |
| **Card** | `.card` + header/body/footer (`:100`) | 51 fichiers (classe) | `bg-white rounded-xl/2xl border` inline : **71×** sur **40 fichiers** | **Faible** — deux mondes coexistent |
| **KPI** | `.kpi`/`.kpi-value`/`.kpi-icon` (`:110`) | **3** fichiers | `text-3xl font-bold` + carte inline ailleurs (`dashboard/partials/kpi_cards.html`, `class_stats.html`, `learn/profile.html`) | Faible |
| **Table** | `.data-table`/`.table-card` (`:121`) | data-table : 3 ; table-card : 8 | 28 `<table>` sur 25 fichiers → la plupart stylées th/td inline | Faible |
| **Badge/pill** | `.badge-*` (8 variantes, `:141`) | 23 refs totales (success 6, danger 6, warning 5, primary 2, neutral 1, info **0**) | pills inline `rounded-full text-xs font-medium` : ~387 `rounded-full` au total ; ex inline `bulletins_main.html:103`, `bulletins_tab.html:17-22` | **Faible** — la grande majorité des badges sont inline |
| **Toast** | `.toast`/`.toast-stack` (`:157`) | 6 (centralisé via `settings/partials/toast.html`, inclus dans `base.html:1265`) | — | **Bonne** (partagé) |
| **Modal** | aucune classe | — | `fixed inset-0` : 32× ; `role="dialog"` : seulement 3× ; backdrop `bg-black/40` : 20× (+`/30`:6, `/20`:6) ; `backdrop-blur` : 24× | Pattern récurrent mais **non factorisé** + a11y inégale (3 `role=dialog` / 32 overlays) |
| **Dropdown** | aucune classe | — | pattern Alpine `x-data{open}` + `x-transition` répété (voir §10) | Récurrent, non factorisé |
| **Onglets (tabs)** | aucune classe | — | inline (`bulletins/`, `accounting/`) | Variable |
| **Pagination** | aucune classe / aucun partial | — | rare, inline | N/A |
| **Tooltip** | aucune | — | repose sur `title=""` natif (sidebar) | N/A |
| **Avatar** | aucune classe | — | pattern répété `w-8/9/10 h-… rounded-full bg-primary-600 text-white` (`base.html:408,425,977,1126`) + version couleur dynamique parent (`base_parent.html:41`) | Récurrent, non factorisé, 2 variantes (statique vs `get_avatar_colors`) |
| **Barre de progression** | aucune classe std | — | `.bar-fill` (parent, inline `<style>`), `.story-pfill` (`student.css:124`), `[data-bar]` JS (parent) | 3 implémentations divergentes |
| **État vide** | aucune classe | — | 81 fichiers contiennent "Aucun…" → pattern récurrent (icône + texte gris) mais **non standardisé** | Variable |
| **Skeleton** | `.skeleton` (`input.css:199`) | **0** | non employé | Mort |
| **Bottom-sheet (mobile)** | `.sheet-item` (`:80`) | 1 (base.html) | 3 sheets répétées dans `base.html` (teacher/staff/account) avec markup quasi identique | Dupliqué intra-fichier |

**Synthèse composants :** une bibliothèque `@apply` correcte existe (boutons, card, badge, table, toast, kpi, input) mais **le taux d'adoption est faible** : pour presque chaque composant, la version inline domine en volume. Plusieurs classes sont **mortes** (`btn-gold`, `skeleton`, `form-label/helper/error`, `badge-info`) et un fichier entier (`components.css`) est orphelin.

---

## 6. ÉTATS

| État | Occurrences (templates) | Couverture |
|---|---|---|
| `hover:` | 657 (140 fichiers) | très large |
| `focus:` | 183 (31 fichiers) | **partielle** — surtout via `.input-field`/`.btn-*` ; rare en inline |
| `focus-visible:` | **0** | absent (a11y clavier sous-traitée) |
| `active:` | 63 | moyenne (scale boutons + tactile) |
| `disabled:` | 20 | faible — surtout `.btn` base |
| `group-hover:` | 26 | ponctuel |
| HTMX `htmx-indicator` | 21 | présent (spinner loading) |
| HTMX `htmx-request` | 2 | quasi absent côté templates (logique dans `<style>` base.html:21-23) |
| `animate-spin` (loading) | 22 | présent |
| Empty state ("Aucun…") | 81 fichiers | large mais non standardisé |

**Constat :** `hover` est très bien couvert ; `focus`/`disabled` sont surtout portés par les classes `@apply` et **chutent dès qu'on passe en inline**. **`focus-visible` totalement absent** → focus clavier non différencié (sévérité majeure a11y). Loading HTMX géré globalement mais peu d'indicateurs locaux.

---

## 7. ICONOGRAPHIE

- **Lucide** appelé via `data-lucide="..."` : **783 occurrences**. Initialisé par `lucide.createIcons()` au `DOMContentLoaded` **et** sur `htmx:afterSwap` (re-render après swap) — pattern présent dans les 4 bases (mais **chaque base réimplémente son propre script d'init**, pas factorisé).
- **SVG inline** : 127 (logos, illustrations, confettis, graphiques décoratifs portail élève/parent).
- **Emojis** : 37 caractères sur 20 fichiers — `✓`(16), `⚠`(7), `🔥`(3, streak élève), `✕`(3), `👋`(2)… Usage mixte emoji/Lucide pour des sémantiques identiques (ex : `✓` emoji vs icône `check`) → incohérence mineure.
- Pas de composant d'icône ; appel direct partout. Cohérence du *mode d'appel* bonne, mais **triple source** (Lucide + SVG inline + emoji).

---

## 8. MOTION

**Tailwind transitions :** `transition*` 1074×. Durées : `duration-200` (83), `duration-150` (57), `duration-300` (29), `duration-500` (7), `duration-250` (3), `duration-100` (3), `duration-700` (1).

**Alpine `x-transition` :** 366 occurrences (dropdowns, sheets, modals) — idiome très récurrent (enter/leave opacity+translate/scale).

**HTMX swaps :** `hx-swap` 117× — `outerHTML` (54), `innerHTML` (48), `none` (7), `outerHTML swap:300ms` (2), `afterbegin` (1). Settling/transitions de swap quasi inexploitées (2 swaps temporisés).

**Animations CSS :**
- Définies en config : `toast-in`/`toast-out` (`tailwind.config.js:99-112`).
- Définies dans `input.css` (`@layer utilities`) : `fadeIn`, `fadeInUp`, `slideInRight`, `slideInUp`, `skeleton`, délais `100→500ms`.
- Classes utilisées dans templates : `animate-spin` (22), `animate-fade-in-up` (22), `animate-fade-in` (11), `animate-delay-*` (10), `animate-slide-in-right` (1).
- **~35 `@keyframes` redéfinis en inline `<style>` dans les templates** (surtout portail élève : `confettiFall`, `starPop`, `quizPop`, `pairSnap`, `orb-drift`, `story-*` dans `student.css`…). Forte fragmentation des animations côté élève.
- `prefers-reduced-motion` respecté dans `input.css:219` et `student.css:127` (positif).

---

## 9. CONFIG TAILWIND — verdict factuel

| Aspect | État |
|---|---|
| `theme.extend` | fontFamily, fontSize (8 paliers), colors (primary/student/gold + 4 sémantiques), boxShadow (sm/md/lg), keyframes+animation toast |
| `content` scanné | `templates/**/*.html`, `apps/**/*.py`, `static/**/*.js` (correct) |
| `safelist` | 2 classes (`lg:left-16`, `lg:left-64`) |
| `plugins` | **aucun** (pas de `@tailwindcss/forms` → styling formulaires 100% manuel) |
| CSS custom | `input.css` (source, 225 l.) ✅ ; `components.css` (51 l.) ❌ **mort/orphelin** ; `student.css` (132 l.) ✅ portail élève ; `output.css` (5825 l., compilé) |
| CSS linké | `output.css` partout (7 bases via static) ; `student.css` uniquement learn ; jamais `components.css` |

**OÙ vivent réellement les styles ?** Verdict : **inline-first**. Preuves chiffrées : 496 `style=""`, 78 hex distincts, `bg-primary-600` inline (131) > `btn-primary` (62 refs) ; cards inline (71) ≈ `.card` (51 fichiers) ; badges inline (≈ majorité des 387 pills) ≫ `.badge-*` (23). La couche `@apply` existe mais n'est pas la voie dominante.

---

## 10. PATTERNS Alpine & HTMX récurrents

### Alpine (idiomes transversaux)
| Pattern | Compteur | Exemples |
|---|---|---|
| `x-data` | 116 | toutes bases |
| `x-show` | 314 | omniprésent |
| `x-transition*` | 366 | dropdowns/modals/sheets |
| `x-cloak` | 167 | anti-FOUC (déclaré dans 3 `<style>` + `student.css:3`) |
| `@click` | 361 | — |
| `$store` | 183 | stores centralisés `base.html:1221-1256` : `sidebar`, `search`, `moreSheet`, `teacherMoreSheet`, `accountSheet`, `confirm` |
| `x-model` | 33 | formulaires |
| Dropdown `x-data="{ open/xxxOpen: false }"` + `@click.away` | récurrent | `base.html:42,593`, `base_student.html:42`, menus utilisateur |
| Modal global `confirm` | 1 store partagé | `base.html:1268-1368` (réutilisable, bon point) |
| Bottom-sheet slide-up (backdrop + panneau + handle) | 3× dans base.html | teacher/staff/account — markup quasi dupliqué |

### HTMX (idiomes transversaux)
| Pattern | Compteur |
|---|---|
| Fichiers utilisant HTMX | 74 / 181 |
| `hx-target` | 116 |
| `hx-swap` | 117 (`outerHTML` dominant) |
| `hx-post` / `hx-get` | 81 / 50 |
| `hx-trigger` | 17 (ex : `keyup changed delay:300ms` recherche globale `base.html:1200`) |
| `hx-boost` | **0** (navigation non boostée) |
| `hx-headers` CSRF global | dans chaque `<body>` (`base.html:30`, parent, …) |
| Re-init Lucide post-swap | dans chaque base | bon réflexe mais dupliqué |

Idiome dominant HTMX : **swap de partials** (`partials/*.html`) ciblant un `#id`, surtout en `outerHTML`. Bien rodé pour tables/listes (student_table_body, payment_list_body, salary_row…).

---

## 11. Partage vs divergence entre portails

### Ce qui est PARTAGÉ (factuel)
- **`output.css` unique** (tokens + composants `@apply`) linké par les 4 portails.
- **Manrope** comme police (même token `font-sans`).
- **Palette `primary` (indigo)** : admin, parent, superadmin, settings.
- **Lucide** comme système d'icônes (mode `data-lucide` partout).
- **Alpine + HTMX** comme runtime, avec `hx-headers` CSRF dans chaque body.
- **Toast** centralisé (`settings/partials/toast.html`, inclus globalement).
- **Composants `@apply`** disponibles pour tous (mais adoption inégale).
- Conventions rayons (lg/xl/2xl/full) et grille d'espacement.

### Où ils DIVERGENT
| Axe | base.html (admin/prof/promoteur) | settings | superadmin | parent | élève (`/learn/`) |
|---|---|---|---|---|---|
| Hérite de | racine | `extends base.html` | base autonome | base autonome | base autonome |
| Couleur de marque | `primary` (indigo) | `primary` | `primary` + bandeau `amber-500` | `primary` (40×) + dérives `green/emerald` | **`student` (emerald)** 15× + violets/near-black hors token |
| Police chargée | self-hosted | (hérité) | self-hosted | self-hosted | **Google Fonts CDN** (divergence) |
| Largeur layout | sidebar + main fluide | sidebar imbriquée | sidebar 56 + topbar | mobile-first plein écran | **`max-w-md mx-auto`** (mobile only) |
| Fond | `bg-gray-50` | (hérité) | `bg-gray-50` | `bg-[#F8F9FC]` (hardcodé) | `bg-[#F0FDF9]` (hardcodé) |
| CSS additionnel | — | — | — | `<style>` bar-fill | **`student.css`** (132 l., 8 node-styles hardcodés + 15 keyframes story) |
| Init JS | scripts stores complets | (hérité) | mini script Lucide | script parent (formatFCFA, data-bar) | script confetti + Lucide |
| Composants `@apply` | utilisés partiellement | utilisés | utilisés | **peu** (markup custom) | **quasi pas** (gamifié, tout custom) |
| Avatar | statique `bg-primary-600` | (hérité) | — | dynamique `get_avatar_colors` | — |

**Lecture :** admin/settings/superadmin forment un **bloc cohérent** (même palette, mêmes composants). Le **parent** est un cousin mobile-first qui réutilise les tokens primary mais réintroduit du hardcodé. L'**élève** est un **sous-design-system à part** (couleur emerald + palette gamifiée hors tokens, font CDN, CSS dédié, animations propres) — c'est la divergence la plus forte, en partie assumée (portail ludique).

---

## 12. Incohérences classées (constat, pas de solution)

| # | Incohérence | Emplacement | Sévérité |
|---|---|---|---|
| 1 | `components.css` mort : token `brand-blue` inexistant + fichier non linké + redéfinit `btn/input/badge` avec d'autres valeurs | `static/css/components.css:1-51` | **Bloquant** (source de vérité ambiguë) |
| 2 | Police élève via Google Fonts CDN alors que le reste est self-hosté (offline/perf) | `learn/base_student.html:8-10` | **Majeur** |
| 3 | Composants `@apply` court-circuités par inline (`bg-primary-600` 131× vs `btn-primary` 62 ; cards inline 71) | transversal | **Majeur** |
| 4 | Triple expression de la couleur de marque : `primary` / `indigo-*` (23) / `blue-*` (53) | transversal | **Majeur** |
| 5 | 78 hex hardcodés dont indigo/success/danger ayant un token (`#4F46E5`×13, `#22C55E`×23, `#EF4444`×21) | 46 fichiers | **Majeur** |
| 6 | Palette élève (violets, ~15 near-black) totalement hors tokens | `learn/*`, `student.css:39-46` | **Majeur** |
| 7 | `focus-visible:` absent (0) — focus clavier non différencié | transversal | **Majeur** (a11y) |
| 8 | a11y modal partielle : 3 `role="dialog"` pour 32 overlays | transversal | Majeur |
| 9 | Tailles typo arbitraires `text-[10px]`(160)/`text-[11px]`(59) doublant `2xs` | transversal | Majeur |
| 10 | Ombres `xl`/`2xl` (36) hors config (sm/md/lg seulement) | transversal | Mineur |
| 11 | Classes mortes : `btn-gold`(0), `skeleton`(0), `form-label/helper/error`(0), `badge-info`(0) | `input.css` | Mineur |
| 12 | Alias sémantiques (`success/warning/danger/info`) quasi inutilisés au profit de `green/amber/red` bruts | transversal | Mineur |
| 13 | 3 implémentations de barre de progression (`bar-fill`, `story-pfill`, `[data-bar]`) | parent/élève | Mineur |
| 14 | Emoji vs Lucide pour mêmes sémantiques (`✓` vs `check`) | 20 fichiers | Mineur |
| 15 | `rounded-md`(36) hors convention rayons | transversal | Mineur |
| 16 | Markup bottom-sheet dupliqué 3× dans base.html | `base.html` | Mineur |

---

*Fin de l'audit. Document généré en lecture seule — aucun fichier source modifié.*
