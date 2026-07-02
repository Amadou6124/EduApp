# Audit UI/UX — Portail Parent (EduApp)

> Audit en **lecture seule**. Aucun fichier applicatif modifié. Périmètre : `templates/parent/` (10 fichiers, 1811 lignes au total).
> Date : 2026-06-28 · Branche : `feature/documents-bulletins-recus`

---

## 0. Chiffres clés

| Métrique | Valeur |
|---|---|
| Templates de pages | 8 (`dashboard, notes, bulletins, payments, annonces, notifications, suivi, account`) |
| Template de base | 1 (`base_parent.html`, 115 lignes) — **distinct de `base.html`** |
| Partials | 2 (`bottom_nav.html` 36 l., `announcement_card.html` 49 l.) |
| Lignes totales `templates/parent/` | 1811 |
| Plus gros fichier | `dashboard.html` (416 l.) |
| Breakpoints responsive (`sm:/md:/lg:/xl:`) | **0** dans tout le portail |
| Blocs HTMX (`hx-*`) | 1 seul usage réel (suppression notif) |
| Occurrences `x-data` (Alpine) | 7 |
| Classes `animate-*` | 25 occurrences |
| Partial mutualisé avec l'admin | 1 (`finance/partials/timeline.html`, mode `readonly=True`) |

---

## 1. Arborescence (page → extends → includes)

| Page | URL name | extends | includes | bottom_nav `active` |
|---|---|---|---|---|
| `dashboard.html` | `parent:dashboard` | `parent/base_parent.html` | `bottom_nav` + `finance/partials/timeline.html` | `home` |
| `bulletins.html` | `parent:bulletins` | `parent/base_parent.html` | `bottom_nav` | `bulletins` |
| `payments.html` | `parent:payments` | `parent/base_parent.html` | `bottom_nav` | `payments` |
| `suivi.html` | `parent:suivi` | `parent/base_parent.html` | `bottom_nav` | `suivi` |
| `account.html` | `parent:account` | `parent/base_parent.html` | `bottom_nav` | `compte` |
| `notes.html` | `parent:notes` | `parent/base_parent.html` | — (header surchargé, pas de bottom_nav block → fallback base = `active=""`) | (vide) |
| `annonces.html` | `parent:annonces` | `parent/base_parent.html` | 2× `announcement_card` | (vide, fallback base) |
| `notifications.html` | `parent:notifications` | `parent/base_parent.html` | — | (vide, fallback base) |
| `base_parent.html` | — | (racine) | `bottom_nav` (avec `active=""`) | — |

**Note** : `notes.html`, `annonces.html`, `notifications.html` ne surchargent **pas** `{% block bottom_nav %}`. Elles héritent donc du `include` par défaut de `base_parent.html` avec `active=""` → **aucun onglet surligné** sur ces 3 écrans (cf. §9, incohérence mineure).

URLs additionnelles (non-templates) : `parent:bulletin-pdf` (PDF, `target="_blank"`), `parent:notif-open`, `parent:notif-delete`, `parent:notif-read-all`, `parent:notif-clear`.

---

## 2. `base_parent.html` disséqué

### 2.1 `<head>` (l. 4-24)

| Élément | Valeur | Ligne |
|---|---|---|
| `lang` | `fr` (codé en dur — l'admin utilise `{{ LANGUAGE_CODE }}`) | 3 |
| viewport | `width=device-width, initial-scale=1.0, viewport-fit=cover` | 6 |
| `viewport-fit=cover` | **présent** (gère les encoches/safe-area iOS) — absent du `base.html` admin | 6 |
| `<title>` | `{% block title %}Espace Parent{% endblock %} — EduApp` | 7 |

### 2.2 Assets chargés (l. 9-14) — strictement le même `vendor/` que l'admin

| Asset | Fichier | Mode |
|---|---|---|
| Police Manrope | `vendor/fonts/manrope/manrope.css` | `<link>` |
| Tailwind | `css/output.css` (build local) | `<link>` |
| HTMX | `vendor/htmx/htmx.min.js` | `defer` |
| Alpine.js | `vendor/alpine/alpine.min.js` | `defer` |
| Lucide | `vendor/lucide/lucide.min.js` | `defer` |
| Chart.js | **absent** | — |

Différence avec l'admin : dans `base.html`, Lucide est chargé **en fin de `<body>`** (l. 1214) ; ici les 3 scripts sont groupés dans le `<head>` avec `defer`.

### 2.3 CSS inline (l. 16-21)

```css
[x-cloak] { display: none !important; }
.bar-fill { transition: width 1s ease-out; }   /* animation barres de progression */
.no-scrollbar { ... }                           /* masque scrollbars (scroll horizontal) */
```

### 2.4 Blocks définis

| Block | Ligne | Rôle |
|---|---|---|
| `title` | 7 | titre onglet |
| `extra_head` | 23 | CSS/JS additionnels par page (utilisé par `notifications.html` seulement) |
| `header` | 33-66 | header complet, surchargeable intégralement |
| `header_left` | 37-45 | avatar parent (cliquable → compte) |
| `header_right` | 49-63 | cloche notifications + badge |
| `main_class` | 69 | classe du `<main>` (jamais surchargé en pratique) |
| `content` | 70 | contenu page |
| `bottom_nav` | 74-76 | bottom-bar (surchargé par 5 pages sur 8) |
| `extra_js` | 112 | JS additionnel |

### 2.5 `<body>` & structure globale (l. 26-28)

```
class="min-h-screen bg-[#F8F9FC] text-gray-900 pb-[calc(68px+env(safe-area-inset-bottom))]"
hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
x-data
```

- Fond global **`#F8F9FC`** (gris très clair, valeur arbitraire hex — l'admin utilise `bg-gray-50`).
- Padding-bottom = `68px + safe-area` → réserve la hauteur exacte de la bottom-nav (68px) + encoche. C'est le mécanisme central du layout mobile.
- `hx-headers` CSRF global (identique à l'admin).

### 2.6 Scripts inline factorisés (l. 79-110) — le « JS commun » du portail

| Bloc | Ligne | Rôle |
|---|---|---|
| Alpine store `parent` | 80-86 | `{ activeChildId, notifCount }` — store global déclaré mais **`activeChildId` jamais lu** dans les templates (les pages utilisent `x-data` local). |
| `lucide.createIcons()` | 92 | rendu icônes au `DOMContentLoaded` |
| `window.formatFCFA(n)` | 95-96 | formatage FCFA global (`Intl.NumberFormat fr-FR` + ` FCFA`) |
| `.js-money` → texte | 99-100 | remplit tous les `.js-money` depuis `data-money` |
| `[data-bar]` → width | 103-105 | anime toutes les barres de progression (via `requestAnimationFrame`) |
| `htmx:afterSwap` → icônes | 109 | recrée les icônes après swap HTMX |

C'est le **pattern signature du portail parent** : montants et barres sont remplis par JS depuis des `data-*`, jamais rendus côté serveur dans le HTML visible (placeholder `—`). `js-money`, `formatFCFA` et `data-bar` n'existent **quasiment pas** dans l'admin (1 seule occurrence : `promoter/school_detail.html`).

---

## 3. HEADER (desktop ET mobile)

Le portail est **mono-layout** : il n'y a pas de version desktop distincte. Le header est une barre fixe de 56px (`h-14`) identique quelle que soit la largeur d'écran.

### 3.1 Header par défaut — dashboard (3 colonnes, l. 34-65)

| Zone | Contenu | Comportement |
|---|---|---|
| Gauche (`header_left`) | Avatar parent rond `w-9 h-9`, initiales, couleurs via `get_avatar_colors` | lien → `parent:account` |
| Centre | `EduApp` en `text-primary-600 font-extrabold` | statique |
| Droite (`header_right`) | Icône `bell` + badge rouge `parent_unread_count` | lien → `parent:notifications` |

Header `sticky top-0 z-40 h-14`, fond blanc, bordure basse.

### 3.2 Header des sous-pages — pattern « retour » (5 pages)

`bulletins, payments, notes, suivi, account, annonces, notifications` surchargent `{% block header %}` avec un header **3 colonnes symétrique** :

- Gauche : flèche `arrow-left` → `parent:dashboard`
- Centre : `<h1 class="flex-1 text-center text-base font-semibold">` titre
- Droite : spacer `w-14` (ou `w-9` sur `annonces`) pour centrer le titre.

**Incohérence mineure** : la largeur du spacer droit varie — `w-14` (payments l.16, notes l.18, bulletins l.16, suivi l.19, account l.16) vs `w-9` (annonces l.14). Le titre n'est donc pas parfaitement centré sur annonces.

`notifications.html` remplace le spacer droit par un bouton **« Tout lire »** (form POST, l. 27-37) quand `unread_count > 0`.

---

## 4. FOOTER / Bottom-nav (`partials/bottom_nav.html`)

C'est **le** composant de navigation du portail. Inclus **6×** (5 pages + base).

### 4.1 Structure (l. 2-36)

```
<nav class="fixed bottom-0 left-0 right-0 z-40 bg-white rounded-t-2xl
            shadow-[0_-4px_12px_rgba(0,0,0,0.08)] border-t border-gray-100">
  <div class="h-[68px] flex"> … 5 items … </div>
  <div style="height: env(safe-area-inset-bottom, 0px)"></div>  <!-- spacer encoche -->
</nav>
```

- Hauteur **68px** + spacer safe-area séparé (cohérent avec le `pb-[calc(68px+...)]` du body).
- Coins supérieurs arrondis (`rounded-t-2xl`), ombre portée vers le haut.

### 4.2 Items (5)

| # | Label | Icône Lucide | Destination | clé `active` |
|---|---|---|---|---|
| 1 | Accueil | `home` | `parent:dashboard` | `home` |
| 2 | Bulletins | `file-text` | `parent:bulletins` | `bulletins` |
| 3 | Paiements | `wallet` | `parent:payments` | `payments` |
| 4 | Suivi | `activity` | `parent:suivi` | `suivi` |
| 5 | Mon compte | `user` | `parent:account` | `compte` |

### 4.3 État actif & accessibilité

- Actif : `text-primary-600` + label `font-semibold` ; inactif : `text-gray-400`.
- Chaque item : `flex-1` (largeur égale), `min-h-[48px]` (cible tactile conforme), `transition-colors`.
- Label en `text-[10px]`.

**Incohérence mineure** : le commentaire d'en-tête (l.1) documente `active` = `home|bulletins|payments|compte` (**4 valeurs**) alors que le nav contient **5 items** et accepte aussi `suivi`. Documentation obsolète.

Comparaison admin : `base.html` a sa propre bottom-nav mobile **par rôle** (teacher/promoter/etc., l. 820-918) avec icônes `w-6 h-6` et hauteur différente ; **aucun code partagé** avec celle du parent.

---

## 5. Navigation complète

- **Primaire** : bottom-nav 5 onglets (toujours visible, sauf qu'elle n'est pas surlignée sur notes/annonces/notifications).
- **Secondaire** : flèche retour vers dashboard sur toutes les sous-pages.
- **Hub central = dashboard** : grille « actions rapides » (l. 180-249) renvoie vers Bulletins, Paiements, Notes (`?child=`), Absences→Suivi (`?child=`). Bannière annonces (l.161) → `parent:annonces`.
- **Sélection enfant multi-enfants** : 3 mécanismes coexistent (cf. §9) :
  - dashboard : liens `?child=<id>` (rechargement serveur) ;
  - notes/suivi : liens `?child=<id>` (rechargement serveur) ;
  - payments : onglets **Alpine `x-show`** (côté client, pas de rechargement).
- **Sorties** : PDF bulletins (`target="_blank"`), déconnexion (form POST sur dashboard état-vide + account).

---

## 6. Écrans (rôle) & comparaison avec l'admin

| Écran | Rôle | Données vues par le parent | Équivalent admin |
|---|---|---|---|
| dashboard | Vue d'ensemble enfant actif : hero solde, timeline financière, annonces, actions rapides, dernier bulletin, absences, messages | Synthèse admin éclatée → **vue mobile condensée mono-enfant** |
| notes | Notes par période/matière (chips devoir/composition, moyenne colorée, barre) | Vue notes admin → **lecture seule, pas de saisie** |
| bulletins | Cartes bulletins par année (moy/rang/1ère moy, appréciation) + PDF Voir/Télécharger | `bulletins:main` admin → **lecture + PDF seulement** |
| payments | Solde + historique transactions groupé par mois (méthode, reçu, montant) | Fiche finance admin → **lecture seule** (cf. §7) |
| suivi | Présences (absences/retards), messages école, appréciations trimestrielles | `students:suivi` admin → **lecture seule** |
| annonces | Annonces école/classe/élève (badges audience) | `schools:announcement-list` → **lecture seule** |
| notifications | Centre de notifs (groupé par date, lu/non-lu, delete HTMX) | `apps/notifications` → consommateur |
| account | Identité parent, enfants liés, déconnexion | profil → **pas d'édition** |

**Conclusion** : le portail parent est **intégralement en lecture seule**. Aucune création/édition de donnée métier. Les seules écritures sont : marquer notif lue, supprimer/effacer notifs, se déconnecter. Le parent voit les **mêmes données** que l'admin mais reformatées en cartes mobiles, mono-enfant, sans aucun contrôle d'édition.

---

## 7. Structure des pages clés

### 7.1 dashboard (416 l.)
Sections : (1) état vide « aucun enfant lié » ; (2) sélecteur avatars multi-enfants ; (2) hero card gradient `primary-600→900` avec statut paiement à 4 états (`no_fee/paid/partial/other`, helper « lot 6bis-B ») ; (2a) **timeline financière mutualisée admin** (`readonly=True`, l.153) ; (2b) bannière annonces ; (3) grille 2×2 actions rapides avec badges (NEW/SOLDE/compteur absences) ; (4) carte dernier bulletin (moy/rang/effectif + PDF) ; (5) absences récentes ; (6) messages école (cartes Alpine « Lire la suite »).

### 7.2 notes
Sélecteur enfant (liens `?child=`) → sections par période (badge En cours/Clôturé) → cartes matière : dot couleur, coeff, moyenne colorée par seuils (≥14 vert / ≥10 ambre / <10 rouge), chips notes (D/C), barre de progression `widthratio`.

### 7.3 bulletins
Groupé par enfant puis par année scolaire (`regroup`). Carte = en-tête gradient `primary-50→indigo-50`, 3 stats (moyenne/rang/1ère moy), appréciation `line-clamp-2`, 2 boutons PDF (**Voir** plein primary + **Télécharger** outline `?download=1`).

### 7.4 payments — **lecture seule, aucun paiement en ligne**
- Pas de bouton « Payer », aucune intégration paiement (Orange Money / Wave sont uniquement des **étiquettes de méthode** sur l'historique, l. 148-160).
- Onglets enfants **Alpine** (`x-data="{ active: 0 }"`, `x-show`).
- Hero card colorée par statut (gris `no_fee` / vert `paid` / ambre `other`), solde `js-money`, barre `data-bar`.
- Historique `regroup by month_group`, icône par méthode, numéro de reçu, montant vert.
- Le parent **constate** son solde et ses versements ; il ne paie pas dans l'app.

### 7.5 suivi
Sélecteur enfant (`?child=`) → hero présences (vert si 0/0, ambre sinon, 2 compteurs absences/retards) → historique absences/retards → messages école (cartes Alpine) → appréciations trimestrielles.

---

## 8. Responsive — **mobile-first strict (mono-layout)**

| Indicateur | Constat |
|---|---|
| Breakpoints Tailwind (`sm:/md:/lg:/xl:`) | **0** dans les 10 fichiers. Le portail ne s'adapte pas au desktop. |
| Largeur de contenu | Marges fixes `mx-4` / `px-4`, jamais de `max-w-*` ni de centrage desktop. Sur grand écran le contenu s'étire pleine largeur. |
| `viewport-fit=cover` + `env(safe-area-inset-*)` | Gérés (body, bottom-nav) → optimisé encoches iOS. |
| Cibles tactiles | bottom-nav `min-h-[48px]`, boutons `h-10`/`h-11`/`h-12`. |
| Feedback tactile | `active:scale-95`, `active:opacity-70`, `active:bg-*` omniprésents (≈ design « app native »). |

**Verdict** : conçu exclusivement pour le mobile. Aucune dégradation/adaptation prévue pour desktop ou tablette. L'admin, à l'inverse, est responsive (`hidden lg:flex` sidebar + bottom-nav mobile).

---

## 9. Composants — variantes, fichier:ligne, cohérence

### 9.1 Boutons

| Variante | Classes | Exemple |
|---|---|---|
| Primaire plein | `bg-primary-600 text-white rounded-xl font-semibold active:bg-primary-700` | dashboard:322-325, bulletins:151 |
| Outline | `bg-white border border-gray-200 text-gray-700 rounded-xl` | bulletins:156 |
| Danger plein | `bg-red-500 text-white rounded-xl` | account:122, notifications:165 |
| Danger doux | `bg-red-50 text-red-500 rounded-2xl` | account:101 |
| Texte/lien | `text-primary-600 text-xs font-medium` | announcement_card:44, notifications:31 |

Rayons mélangés : `rounded-xl` vs `rounded-2xl` selon contexte (pas d'échelle stricte). L'admin utilise une classe utilitaire `.btn-primary` (components.css) ; le portail parent **n'emploie pas `.btn-primary`** sauf via le partial timeline mutualisé (`finance/partials/timeline.html:31`, masqué en readonly) → **divergence de système de boutons** entre les deux portails.

### 9.2 Cards
- Carte standard : `bg-white rounded-2xl shadow-sm` (+ parfois `border border-gray-100`). Rayon dominant `rounded-2xl`.
- Hero cards : `rounded-3xl` + gradient (`from-primary-600 to-primary-900` dashboard ; couleurs par statut payments/suivi).
- Liste-cards : conteneur `rounded-2xl overflow-hidden` + lignes séparées par `border-b border-gray-50`.

### 9.3 Badges / pills
| Usage | Classes | Fichier:ligne |
|---|---|---|
| Audience annonce | `bg-primary-100/indigo-100/amber-100 text-*-700 rounded-full text-[10px]` | announcement_card:10-22 |
| NEW / SOLDE | `bg-green-500/red-500 text-white rounded-full text-[9px]` | dashboard:187,204 |
| Compteur (notif/absence) | `bg-red-500 text-white rounded-full min-w-[16px]` | base_parent:56, dashboard:236 |
| Statut période | `bg-amber-100/green-100 rounded-full text-[10px]` | notes:82-88 |
| Rôle « Parent » | `bg-primary-100 text-primary-700 rounded-full` | account:38 |
| Type observation | behaviour/academic/health/autre, palettes divergentes (cf. ci-dessous) | dashboard/suivi |

### 9.4 Barres de progression
Pattern unique : `<div class="bar-fill ..." style="width:0%" data-bar="{{ pct }}">` animé par le JS de base (l.103-105). Présent : dashboard:123, payments:112, notes:136.

### 9.5 États vides (8 occurrences)
Pattern très cohérent : cercle gris `w-20 h-20 rounded-full bg-gray-100` (ou `bg-primary-50` sur dashboard) + icône Lucide `text-gray-300` + titre `text-gray-700` + sous-texte `text-gray-400`. Deux niveaux : **global** (`min-h-[60vh]`) et **par enfant** (carte compacte `p-6`).

### 9.6 Onglets / sélecteur enfant — **3 implémentations divergentes (incohérence majeure)**

| Page | Mécanisme | fichier:ligne | Rechargement |
|---|---|---|---|
| dashboard | liens `?child=` + avatars de tailles différentes (actif `w-14`, inactif `w-11 opacity-60`) | dashboard:36-57 | serveur |
| notes | liens `?child=` + bloc `bg-white shadow border` actif / `opacity-50` inactif | notes:44-63 | serveur |
| suivi | identique notes | suivi:49-67 | serveur |
| payments | onglets **Alpine** `@click="active=N"` + `x-show` | payments:46-66 | client |

→ Trois UX différentes pour la même tâche « choisir l'enfant » selon l'écran.

### 9.7 Toasts
**Aucun toast** dans le portail parent (le système de toasts/`$store.confirm` vit dans `base.html` admin, l.1297+, non importé ici).

### 9.8 Comparaison de fond avec l'admin

| Aspect | Parent | Admin (`base.html`) |
|---|---|---|
| Base template | `base_parent.html` (115 l.) | `base.html` (1372 l.) |
| Layout | mono mobile, bottom-nav | sidebar `lg:` + bottom-nav par rôle |
| Fond body | `bg-[#F8F9FC]` (hex) | `bg-gray-50` |
| Lucide | `<head> defer` | fin de `<body>` |
| Chart.js | absent | présent (dashboards admin/promoter/accounting) |
| Toasts/confirm modale | absents | présents (Alpine store global) |
| `js-money`/`formatFCFA`/`data-bar` | cœur du portail | quasi absents (1 fichier) |
| Couleur primaire | `primary-*` (palette Tailwind partagée) | `primary-*` (idem) |

**Ce qui est partagé** : la palette `primary-*`, la police Manrope, le même `vendor/` (HTMX/Alpine/Lucide), Tailwind `output.css`, et **un seul partial** (`finance/partials/timeline.html`, réutilisé en `readonly`).
**Ce qui est dupliqué / spécifique** : base, header, bottom-nav, états vides, cards, badges, helper monétaire JS — tout est ré-implémenté côté parent.

---

## 10. Patterns HTMX & Alpine récurrents

### 10.1 HTMX — usage minimal (1 vrai cas)
| Pattern | fichier:ligne |
|---|---|
| `hx-headers` CSRF global | base_parent:27 |
| Suppression notif (`hx-post` + `hx-target` + `hx-swap="outerHTML swap:300ms"`) + CSS `.notif-card.htmx-swapping` (slide-out) | notifications:121-128 + 8-12 |
| `htmx:afterSwap` → `lucide.createIcons()` | base_parent:109 |

Toutes les autres mutations (tout lire, effacer, déconnexion) sont des **forms POST classiques**, pas HTMX.

### 10.2 Alpine — patterns
| Pattern | fichier:ligne |
|---|---|
| Store global `parent` (`activeChildId` non utilisé, `notifCount`) | base_parent:80-86 |
| **« Lire la suite »** : `x-data="{expanded,overflow}"` + `x-init` mesure `scrollHeight>clientHeight` + `line-clamp` toggle | announcement_card:1-2/36-45, dashboard:374-404, suivi:165-208 (3 duplications quasi identiques) |
| Onglets enfants `x-data="{active:0}"` + `x-show` + `x-cloak` | payments:40,73 |
| Confirmation destructive `x-data="{confirm}"` (déconnexion / effacer) | account:97-129, notifications:140-172 |
| `[x-cloak]` masquage initial | base_parent:17 |

Le pattern « Lire la suite » est **dupliqué 3 fois** sans factorisation en partial.

---

## 11. Incohérences relevées (lecture seule — aucun correctif appliqué)

| # | Description | fichier:ligne | Sévérité |
|---|---|---|---|
| I1 | Sélecteur enfant implémenté de 3 façons différentes (liens serveur dashboard/notes/suivi vs onglets Alpine payments) → UX incohérente | dashboard:36 / notes:44 / suivi:49 / payments:46 | **Majeur** |
| I2 | Bottom-nav non surlignée sur notes/annonces/notifications (block non surchargé → `active=""`) ; de plus notes/annonces/notifications n'ont aucun onglet correspondant | notes/annonces/notifications | **Majeur** |
| I3 | Système de boutons divergent du reste de l'app : `.btn-primary` (components.css) non utilisé, classes ré-écrites à la main ; rayons `rounded-xl`/`rounded-2xl` mélangés | dashboard:322, bulletins:151,156 | Majeur |
| I4 | Palettes des types d'observation divergentes entre dashboard et suivi : behaviour = `orange-*` (dashboard:377/383) vs `amber-*` (suivi:168/178) ; academic = `blue-*` vs `indigo-*` | dashboard:377-394 / suivi:168-196 | Mineur |
| I5 | Largeur du spacer header droit variable (`w-14` partout vs `w-9` sur annonces) → titre non centré sur annonces | annonces:14 vs payments:16 | Mineur |
| I6 | Commentaire d'en-tête bottom_nav obsolète (`home\|bulletins\|payments\|compte`, 4 valeurs) alors que 5 items dont `suivi` | bottom_nav:1 | Mineur |
| I7 | Store Alpine `parent.activeChildId` déclaré mais jamais lu (code mort) | base_parent:82 | Mineur |
| I8 | Pattern « Lire la suite » dupliqué 3× au lieu d'un partial | announcement_card / dashboard:374 / suivi:165 | Mineur |
| I9 | Couleur de fond en hex arbitraire `bg-[#F8F9FC]` (et `top-14` codé en dur pour les labels sticky) au lieu d'un token Tailwind | base_parent:26 ; notifications:66 / annonces:39 | Mineur |
| I10 | Aucune balise `<title>` traduisible ni `lang` dynamique (codé `fr`) alors que l'admin gère i18n | base_parent:3,7 | Mineur |

---

## 12. Synthèse

Le portail parent est un **mini-site mobile autonome** : sa propre base (`base_parent.html`), sa propre navigation (bottom-nav 5 onglets), son propre helper monétaire JS. Il est **strictement en lecture seule** (aucun paiement en ligne, aucune édition), **mobile-first sans aucun breakpoint**, et soigné côté micro-interactions (animations `fade-in`, `active:scale-95`, safe-area iOS). Il **réutilise très peu** de l'admin : palette `primary`, fonts, vendor JS, et un unique partial finance (`timeline.html`, readonly). Tout le reste (header, cards, badges, états vides, boutons) est dupliqué et présente quelques divergences (3 sélecteurs d'enfant, boutons hors `.btn-primary`, palettes d'observation).
