# Audit UI/UX exhaustif — EduApp

> **Nature :** audit en lecture seule, préparatoire au refonte UI/UX complet des 4 portails.
> Aucun fichier de l'application (template, CSS, JS, config) n'a été modifié. Le seul livrable
> est cette documentation.
> **Date :** 2026-06-28 · **Branche :** `feature/documents-bulletins-recus` · **Stack :** Django +
> Tailwind + Alpine.js + HTMX + Chart.js + Lucide + Manrope.

---

## Sommaire

| Doc | Contenu |
|---|---|
| **00-index.md** (ce fichier) | Méthodologie, périmètre, synthèse exécutive |
| [01-portail-admin.md](01-portail-admin.md) | Portail Direction/Admin (gestion + finance + settings + superadmin + promoteur + team) |
| [02-portail-enseignant.md](02-portail-enseignant.md) | Portail Enseignant (notes, présences, difficultés, observations, unités) |
| [03-portail-parent.md](03-portail-parent.md) | Portail Parent (mobile-first, lecture seule) |
| [04-portail-eleve.md](04-portail-eleve.md) | Portail Élève (apprentissage gamifié, état hybride V1/V2) |
| [10-design-system-transversal.md](10-design-system-transversal.md) | Le « design system de facto » : couleurs, typo, espacement, composants, motion |
| [20-incoherences.md](20-incoherences.md) | Registre des incohérences classé par sévérité |
| [30-recommandation-architecture.md](30-recommandation-architecture.md) | Recommandation stratégique (option a/b/c) |

---

## Méthodologie suivie

1. **Recon & cartographie** (passe 1, inventaire brut) : identification de la stack, du périmètre réel
   (181 templates HTML centralisés dans `templates/`, hors `node_modules`/`venv`), et mapping de chaque
   template à son template de base via les directives `{% extends %}` / `{% include %}`.
2. **Audit parallèle** (passe 2, classification) : **5 sous-agents lancés en parallèle** — un par portail
   + un agent transversal dédié au design system — chacun travaillant en lecture seule sur un périmètre
   exclusif et produisant son propre document. Chaque agent a reçu le contexte technique pré-établi pour
   ne pas le re-dériver.
3. **Détection des incohérences** (passe 3) : chaque agent a tenu un registre local (fichier:ligne +
   sévérité) ; ces registres ont été **consolidés et re-classés** sur une échelle unique dans
   `20-incoherences.md`.
4. **Synthèse & recommandation** (passe 4) : analyse du partage vs divergence inter-portails et
   recommandation d'architecture argumentée dans `30-recommandation-architecture.md`.

**Principes appliqués :** lecture réelle des fichiers (pas de supposition), citation systématique des
chemins + numéros de ligne, quantification de tout (compteurs grep), aucune proposition de design (constat
de l'existant uniquement — seule exception : le registre des incohérences à corriger).

---

## Périmètre cartographié

**4 templates de base** (+ 1 sous-base) structurent toute l'application :

| Base | `extends` | Portail(s) servi(s) |
|---|:--:|---|
| `templates/base.html` | 38 | Admin + Enseignant (coque commune : sidebar `lg:`, header, bottom-nav, bottom-sheets) |
| `templates/superadmin/base_superadmin.html` | 11 | Superadmin (sans Alpine/HTMX) |
| `templates/settings/settings_base.html` | 9 | Réglages (étend lui-même `base.html`) |
| `templates/parent/base_parent.html` | 8 | Parent (mobile-first autonome) |
| `templates/learn/base_student.html` | 2 | Élève V1 (résiduel) |
| *(aucune base)* | — | Élève V2 : 6 templates `*_v2.html` full-HTML autonomes |

| Portail | Dossiers `templates/` | Écrans (≈) | Base |
|---|---|:--:|---|
| Admin/Direction | dashboard, schools, students, accounting, finance, payments, bulletins, settings, superadmin, promoter, team, accounts, erreurs | ~40 | `base.html` (+2) |
| Enseignant | teachers, lessons, notes | ~12 | `base.html` |
| Parent | parent | 8 | `base_parent.html` |
| Élève | learn, student_learning | ~10 | `base_student.html` (V1) + V2 autonomes |

---

## Synthèse exécutive

### Le constat central
EduApp **possède un design system « de facto » déclaré mais non adopté.** Les tokens (couleurs
sémantiques, échelle typo 8 paliers, espacement, rayons) et des composants `@apply` (`btn-primary`,
`card`, `input-field`, `badge-*`) existent proprement dans `tailwind.config.js` + `input.css` — mais
l'usage réel est **massivement inline et fragmenté**. Le système est *écrit*, pas *utilisé*.

### Les chiffres qui le prouvent (transversal)
| Indicateur | Valeur | Lecture |
|---|---|---|
| Bouton primaire | **131** `bg-primary-600` inline **vs 62** `.btn-primary` | composant court-circuité |
| Cards | **71 inline vs `.card`** (51 fichiers) | idem |
| Badges/pills | **~387 inline vs 23** `.badge-*` | idem |
| Couleur de marque | **3 expressions** : `primary` / `indigo-*`(23) / `blue-*`(53) | fragmentation |
| Hex hardcodés | **78 distincts** sur 46 fichiers (`#22C55E`×23, `#EF4444`×21…) | dont beaucoup ont déjà un token |
| Tailles typo arbitraires | **228** (`text-[10px]`×160) | contournent l'échelle |
| `style=""` inline | **496** | dette de style brute |
| `focus-visible:` | **0** | a11y clavier absente |
| Icônes | **783** Lucide + **127** SVG inline + **37** emojis | triple source |
| Fichiers CSS morts | **2** (`components.css`, `student.css` quasi) | pièges actifs |

### L'état des 4 portails en une ligne chacun
- **Admin** — le bloc le plus cohérent et le plus riche (HTMX/Alpine denses, settings exemplaire), mais
  ~73 états vides non factorisés, cloche notifications inerte, superadmin divergent, CDN sur l'auth.
- **Enseignant** — partage `base.html` avec l'admin ; sommet de complexité responsive avec **deux UX
  entièrement distinctes** pour la saisie de notes (table desktop vs clavier custom mobile, bascule à `sm`),
  mais sous-utilise les utilitaires partagés et duplique de la logique JS.
- **Parent** — **mini-site mobile autonome** (base à part, 0 breakpoint, bottom-nav 5 onglets), **100 %
  lecture seule** (aucun paiement en ligne), soigné en micro-interactions ; réutilise les tokens mais
  duplique tous ses composants et son sélecteur d'enfant (3 implémentations).
- **Élève** — **refonte V2 ~80 % faite mais inachevée** : V1 supprimé, 6 écrans V2 autonomes sophistiqués
  (state machines Alpine, correction serveur anti-triche), mais 8 types de questions manquants, onglets
  vides, profil/notes restés en V1, `student.css` mort, font CDN, doc périmée. **Le portail le plus
  divergent** — un sous-design-system sombre gamifié à part entière.

### Ce qui est partagé vs divergent
Le socle réellement commun se limite à : palette `primary`, Manrope, bundle vendor, Lucide, `output.css`.
**Un seul partial traverse deux portails** (`finance/partials/timeline.html`). Les divergences
**structurelles** (parent et élève autonomes) sont **intentionnelles et justifiées par l'audience** ;
les divergences **de détail** (couleurs, polices, composants, onglets) sont **accidentelles** et
constituent l'essentiel de la dette.

### Incohérences (registre complet : [20-incoherences.md](20-incoherences.md))
**3 bloquantes · 21 majeures · 30+ mineures.** Les 3 bloquantes : `components.css` mort et contradictoire,
`student.css` orphelin encore chargé, exam runner à 5/13 types (spec non livrée).

### Recommandation (détail : [30-recommandation-architecture.md](30-recommandation-architecture.md))
**Option (b) — système unifié + élève à part**, raffinée en **3 strates** : une couche de **tokens
commune aux 4 portails**, puis une **lib « gestion » (admin + enseignant + parent)** et une **lib « learn »
gamifiée (élève)**. Justification : le socle commun existe déjà à 80 % (unification à coût faible) ; admin
et enseignant partagent déjà `base.html` et le parent réutilise les tokens (lib gestion = évolution
naturelle) ; le portail élève est objectivement un autre produit (0 HTMX, thème sombre, mobile-only) dont
la séparation est déjà engagée et doit être **finie fonctionnellement avant** d'être rebranchée sur le socle.

---

*Tous les sous-documents ont été produits en lecture seule. Aucun template, style ou config de
l'application n'a été modifié au cours de cet audit.*
