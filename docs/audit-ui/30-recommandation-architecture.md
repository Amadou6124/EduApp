# Recommandation d'architecture du design system — EduApp

> Livrable stratégique de l'audit. Réponse factuelle aux trois questions imposées :
> ce que les portails **partagent**, où ils **divergent** (intentionnel ou accidentel), et
> quelle **architecture** adopter parmi (a) système unifié pour les 4, (b) système unifié + élève
> à part, (c) traitement indépendant par portail.

---

## 1. Ce que les 4 portails partagent RÉELLEMENT aujourd'hui (preuves)

| Actif partagé | Admin | Enseignant | Parent | Élève | Preuve |
|---|:--:|:--:|:--:|:--:|---|
| Template de base `base.html` | ✅ | ✅ | ❌ | ❌ | 38 `extends "base.html"` ; parent/élève ont leur propre base |
| Feuille compilée `static/css/output.css` | ✅ | ✅ | ✅ | ✅ partiel | chargée par toutes les bases sauf les V2 autonomes (CSS inline) |
| Token couleur `primary-*` | ✅ | ✅ | ✅ | ❌ | élève = palette violette hors tokens [transversal §3] |
| Police **Manrope** | ✅ self-hosté | ✅ self-hosté | ✅ self-hosté | ⚠️ **CDN** | `base_student.html:8-10` diverge [MAJ-2] |
| Vendor JS (Alpine, HTMX, Lucide) | ✅ | ✅ | ✅ | ⚠️ HTMX=0 | élève n'utilise pas HTMX (fetch natif) [élève §10] |
| Icônes **Lucide** (`data-lucide`, 783 occ.) | ✅ | ✅ | ✅ | ✅ | + 127 SVG inline + 37 emojis en parasites [transversal §7] |
| Toasts centralisés + `$store.confirm` | ✅ | ✅ | ❌ | ❌ | propres à `base.html` |
| Partial mutualisé inter-portail | — | — | ✅ | — | **un seul** : `finance/partials/timeline.html` (parent en `readonly=True`) [parent §12] |

**Verdict factuel.** Le socle réellement partagé se réduit à : une **palette `primary`**, **Manrope**,
le **bundle vendor**, **Lucide**, et **une feuille `output.css`** générée depuis un `tailwind.config.js`
unique. Au niveau composant, le partage est **quasi nul** : un seul partial traverse deux portails.
Admin + Enseignant partagent en plus toute la coque `base.html` (sidebar, header, bottom-sheets).

---

## 2. Où divergent-ils — et est-ce intentionnel ou accidentel ?

| Divergence | Portails | Nature | Verdict |
|---|---|---|---|
| Base séparée mobile-first, 0 breakpoint, bottom-nav 5 onglets | Parent | **Intentionnelle** — public mobile, lecture seule | ✅ Légitime |
| Base séparée, thème sombre gamifié, state machines Alpine, mobile-only | Élève | **Intentionnelle** — refonte V2 from-scratch d'après maquette React | ✅ Légitime |
| Pas d'Alpine/HTMX, navbar `primary-900`, pas de recherche | Superadmin | **Semi-intentionnelle** — portail technique à faible trafic, mais double layout à maintenir | ⚠️ À rationaliser |
| Police via Google Fonts CDN | Élève | **Accidentelle** — régression vs self-hosted partout ailleurs | ❌ À corriger [MAJ-2] |
| `student.css` mort encore chargé | Élève | **Accidentelle** — séquelle de la suppression du V1 | ❌ À corriger [BLK-2] |
| `components.css` mort et contradictoire | Tous | **Accidentelle** — fichier fantôme | ❌ À corriger [BLK-1] |
| Composants réécrits inline au lieu de `@apply` | Admin, Enseignant, Parent | **Accidentelle** — discipline non tenue (131 inline vs 62 classe) | ❌ À corriger [MAJ-4] |
| Triple couleur de marque `primary`/`indigo`/`blue` | Tous sauf élève | **Accidentelle** — dérive progressive | ❌ À corriger [MAJ-7] |
| 3 sélecteurs d'enfant, 3 systèmes d'onglets (×2 portails) | Parent, Admin, Enseignant | **Accidentelle** — absence de composant canonique | ❌ À corriger |

**Synthèse.** Les divergences **structurelles** (parent et élève autonomes) sont **intentionnelles
et justifiées par l'audience**. Les divergences **de détail** (couleurs, polices, composants, onglets)
sont **accidentelles** et représentent l'essentiel de la dette : ce sont elles que le refonte doit
absorber, pas les premières.

---

## 3. Les trois options évaluées

### Option (a) — Un système de design unifié pour les 4 portails
Forcer admin, enseignant, parent **et** élève sous une même bibliothèque de composants et une même coque.

- ➕ Cohérence maximale, une seule source de vérité.
- ➖ **Contredit les faits** : le portail élève est un produit gamifié (thème sombre, animations,
  machines à états, mobile-only, sans HTMX) dont les besoins n'ont presque aucun recouvrement avec un
  tableau de bord de gestion. Le forcer dans la coque admin reviendrait à **défaire la refonte V2** en cours.
- ➖ Le portail parent (lecture seule, 0 breakpoint) et l'admin (sidebar `lg:`, tables denses) n'ont pas
  les mêmes layouts ; un composant unique serait sur-paramétré.
- **Rejetée.**

### Option (c) — Traitement indépendant par portail
Quatre design systems autonomes.

- ➕ Liberté maximale par portail.
- ➖ **C'est déjà la situation actuelle de fait, et c'est précisément la cause de la dette** : 4 façons
  de faire un bouton, triple couleur de marque, 78 hex hardcodés, font CDN, composants dupliqués. Officialiser
  cet état multiplierait la maintenance par 4 sans corriger aucune incohérence.
- **Rejetée.**

### Option (b) — Système unifié + portail élève traité à part ✅ **RECOMMANDÉE**
Un design system unifié pour **admin + enseignant + parent**, et le **portail élève en système gamifié
distinct**, les deux **assis sur une couche de tokens commune**.

---

## 4. Recommandation détaillée — Option (b) raffinée : « socle commun, deux couches composants »

Architecture en **trois strates** :

```
┌─────────────────────────────────────────────────────────────┐
│  STRATE 1 — CORE TOKENS (partagée par les 4 portails)        │
│  couleurs sémantiques · échelle typo · espacement · rayons   │
│  ombres · Manrope SELF-HOSTÉ · Lucide · primitives de motion │
│  → tailwind.config.js unique, source de vérité unique        │
└─────────────────────────────────────────────────────────────┘
        │                                          │
        ▼                                          ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  STRATE 2a — LIB « GESTION »  │    │  STRATE 2b — LIB « LEARN »    │
│  Admin · Enseignant · Parent  │    │  Élève (gamifié, thème sombre)│
│  base.html + base_parent.html │    │  base_student V2 (autonome    │
│  boutons, cards, tables,      │    │  assumé), runners Alpine,     │
│  modals, badges, forms, nav   │    │  XP/streak, confetti unifié,  │
│  (composants @apply canoniques)│   │  animations, mobile-only      │
└──────────────────────────────┘    └──────────────────────────────┘
```

**Pourquoi (b) et pas (a) ni (c) — argumenté par l'audit :**

1. **Le socle commun existe déjà à 80 %** (palette `primary`, Manrope, Lucide, vendor, `output.css`).
   L'unifier formellement est un coût **faible** et supprime d'un coup MAJ-7, MAJ-8, MAJ-2 et la moitié
   des mineures.
2. **Admin + Enseignant partagent littéralement `base.html`** et **Parent réutilise déjà les tokens** :
   les fondre dans une seule lib « gestion » est l'évolution naturelle, pas une refonte. La majorité de
   la dette de ces 3 portails (MAJ-4, MAJ-5, MAJ-6, sélecteurs/onglets dupliqués) se résout en
   **adoptant réellement les composants `@apply` déjà déclarés**.
3. **Le portail élève est objectivement un autre produit** : 0 HTMX, thème sombre hors tokens, 6 écrans
   full-HTML autonomes, state machines Alpine, mobile-only strict. Le traiter à part **valide la direction
   déjà prise** par la refonte V2 — mais en le **rebranchant sur la Strate 1** (font self-hostée, accent
   `#6d28d9` devenu token, motion primitives partagées) pour effacer les divergences *accidentelles*
   (MAJ-2, MIN-24/26) sans toucher à son identité visuelle.

**Ce que cette architecture impose comme décisions préalables (cf. registre) :**

| Décision | Incohérences résolues |
|---|---|
| Supprimer `components.css` et `student.css` morts ; figer `input.css` comme **unique** source `@apply` | BLK-1, BLK-2, MIN-35 |
| Une seule couleur de marque (`primary`) ; bannir `indigo-*`/`blue-*`/hex bruts | MAJ-7, MAJ-8, MAJ-9, MIN-1, MIN-2 |
| Politique « 100 % self-hosted » (font, JS) appliquée partout, y compris auth & élève | MAJ-1, MAJ-2 |
| Règle « pas de style inline pour un composant qui a une classe » + composants canoniques (bouton, card, badge, modal, table, onglets, sélecteur d'enfant, état vide) | MAJ-4, MAJ-5, MAJ-6, MAJ-16, MIN-3→7, MIN-11 |
| Standard a11y minimal : `focus-visible`, `role="dialog"`, ne plus bloquer le zoom | MAJ-10, MAJ-11, MAJ-12 |
| Échelle responsive unique et documentée (trancher `sm` vs `lg` comme breakpoint structurant) | MAJ-13, MAJ-14 |

---

## 5. Portée du portail élève : un chantier produit, pas seulement design

L'audit établit que la refonte V2 est **~80 % faite mais inachevée** (BLK-3, MAJ-21, dette D1→D9). Ce
portail ne doit **pas** être inclus dans le premier lot du refonte design : il faut d'abord **finir la V2
fonctionnellement** (8 types de questions manquants, onglets Pratique/Révision, migration profil+notes en
thème sombre, suppression du résiduel V1) **puis** le rebrancher sur la Strate 1. L'inclure trop tôt dans
un système unifié reviendrait à figer un design system sur une base mouvante.

---

## 6. Séquencement recommandé (sans solution de design, juste l'ordre logique)

1. **Lot 0 — Assainissement** : supprimer le CSS mort, trancher la source de vérité, unifier la couleur de
   marque et la politique d'assets. (Résout les 3 bloquants + la plupart des majeures transversales.)
2. **Lot 1 — Strate 1 (tokens)** : `tailwind.config.js` consolidé, font self-hostée partout, Lucide unique.
3. **Lot 2 — Strate 2a (lib gestion)** : composants canoniques adoptés sur admin → enseignant → parent.
4. **Lot 3 — Finition fonctionnelle V2 élève** (piloté produit), **puis** rebranchement sur la Strate 1.
5. **Lot 4 — Strate 2b (lib learn)** : formalisation du système gamifié sur le socle commun.

> **En une phrase :** *Option (b) — un design system unifié « gestion » (admin + enseignant + parent) et
> un système « learn » gamifié distinct pour l'élève, tous deux posés sur une couche de tokens unique ;
> les divergences structurelles sont conservées car intentionnelles, les divergences accidentelles
> (couleurs, polices, composants dupliqués, CSS mort) sont éliminées.*
