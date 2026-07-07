# Chantier — Périodes par cycle

Branche : `feature/periodes-par-cycle`
Statut : **EN COURS** — périmètre validé **K-12 (Fondamental + Secondaire)**, supérieur/LMD hors périmètre.

## Objectif
Les périodes d'évaluation ne sont plus communes à toute l'école : elles dépendent
du **cycle**. Un cycle a son propre jeu de périodes.

- **1er cycle (1ère→6ème)** → **compositions** (ex. 4 compositions)
- **2nd cycle (7ème→9ème)** → **trimestres** (ex. 3 trimestres)

Fondé sur la réalité malienne : le fondamental est en 2 cycles, le 1er tourne en
compositions, le 2nd en trimestres, et le calendrier varie par cycle.

## Recherche — rythmes d'évaluation par cycle (Mali)
Vérifié par recherche (sources en bas). Les cycles que l'app déclare gérer n'ont
pas le même rythme — c'est le cœur du chantier.

| Cycle | Classes | Rythme réel | Diplôme |
|---|---|---|---|
| Préscolaire | Jardin d'enfants | **Aucune note** (socialisation/observation) | — |
| Fondamental 1er cycle | 1ère→6ème | **Compositions** (mensuelles + trimestrielles cumulées → moyenne annuelle) | (DEF) |
| Fondamental 2nd cycle | 7ème→9ème | 3 trimestres + compositions | **DEF** |
| Secondaire général (lycée) | 10ème→12ème | **3 trimestres** (contrôle continu + compo) | **BAC** |
| Secondaire technique/pro | CAP 2 ans / BT 4 ans | Trimestres | CAP / BT |
| Supérieur (université) | Licence/Master/Doctorat | **Semestres** (LMD : 30 crédits, UE, 10/20 compensation) | L/M/D |

**Conséquences :**
- 3 types de périodes nécessaires : `COMPOSITION` · `TRIMESTRE` · `SEMESTRE`.
- Nombre **variable** (ne jamais coder « 4 ») → le directeur choisit.
- Préscolaire = **cycle normal** (les jardins d'enfants ont déjà des bulletins) → on ne
  désactive rien, il a sa section comme les autres.
- ⚠️ **Supérieur (LMD) HORS PÉRIMÈTRE** : le modèle `Note`/`Bulletin` (moyenne/20 + rang)
  ne convient pas aux crédits/UE. L'app est positionnée **Fondamental + Secondaire (K-12)**.

## Décision de design
**Cible durable = « par cycle par défaut, surcharge par classe possible »** (règle générale +
exception). On l'atteint en 2 étapes sûres et additives, sans rework :
- **Étape A (démo)** : réglage par cycle ; chaque classe hérite de son cycle.
- **Étape B (après)** : surcharge optionnelle par classe (6ème hybride, 9ème à 2 trim.).
  Add-on propre : l'app raisonne déjà *au niveau de la classe*, le cycle n'est que la
  réponse par défaut. Résolution cible : **classe → cycle → école (NULL)**.

Détails :
- Granularité **par cycle** (`SchoolClass.level` = `fondamental_1` / `fondamental_2` / …).
- **3 types** de périodes : ajouter `COMPOSITION` à côté de `TRIMESTER` / `SEMESTER`.
- **Rétro-compatible** : une école mono-structure garde ses périodes « sans cycle »
  (comportement actuel préservé, aucune migration de données risquée).
- **Grille-ready** : le résolveur prend une *classe* en entrée (pas un cycle). Passer
  plus tard à une grille fine par classe (6ème hybride, 7-9ème à 2 ou 3 trimestres)
  = changer l'intérieur du résolveur, **PAS les ~162 points d'appel**.

## Le changement de modèle (`apps/schools/models.py :: Period`)
1. Ajouter `education_level` (nullable, `EducationLevel.choices`).
   - `NULL` = s'applique à toute l'école (legacy / école simple).
   - `fondamental_1` = ne s'applique qu'aux classes du 1er cycle. Etc.
2. Ajouter le type `COMPOSITION` aux `period_type` existants (TRIMESTER/SEMESTER/CUSTOM).
3. Contrainte d'unicité `(school_year, name)` → `(school_year, education_level, name)`.
4. Migration : défaut `NULL` → les périodes existantes ne changent pas de comportement.
5. **Dates optionnelles** : `start_date` / `end_date` deviennent `null=True`. Le directeur
   ne connaît pas les dates à l'avance (grèves, imprévus) → il pose la structure (nb de
   compositions), et le vrai signal « période en cours » est **`is_notes_open`** (basculé
   à la main). Finances (`_due_dates_for_year`) : fallback sur découpage égal de l'année
   si les dates de période sont absentes.

## La pièce maîtresse : un résolveur central (n'existe pas aujourd'hui)
`apps/schools/periods.py` (nouveau) :
- `periods_for_class(school_class, school_year=None)` → périodes du cycle de la classe ;
  fallback sur les périodes `education_level IS NULL` si le cycle n'en a pas.
- `periods_for_student(student, ...)` → via `student.school_class`.
- `resolve_active_period(request, periods, param='period')` → sélection courante.

Tout le reste route à travers ce module (source unique).

## Étapes ordonnées (chaque lot = testable indépendamment)
0. ✅ **Audit précis** — ~25 vrais points de résolution isolés (le reste = `period=period` en aval, inchangé).
1. ✅ **Modèle + migration** `0023` (COMPOSITION + `education_level` nullable + contraintes conditionnelles). Non-destructif, périodes NULL préservées.
2. ✅ **Résolveur central** `apps/schools/periods.py` (`periods_for_class/student/cycle`, `resolve_active_period`, `active_year_for`). Fallback cycle→NULL vérifié sur données réelles.
3. ✅ **UI config** (Paramètres → Périodes) : sections par cycle auto-détectées, génération
   par cycle (compositions/trimestres × nombre), **dates optionnelles** (migration `0024`),
   section « Toute l'école » legacy, garde-fou notes. Testé backend (rollback) + live sur
   Sundiata (2 cycles + legacy), 0 erreur console.
4. ✅ **Saisie des notes** : `notes_views.py::notes_dashboard` (onglets périodes limités aux
   cycles présents ; grille filtrée au cycle de la période) + `teachers/views.py` (dashboard,
   difficulté, détail élève, quick-assess → résolution **par classe**). ⚠️ `notes_views.py`
   manquait dans l'audit initial. Testé en rollback : grille compo = 1er cycle only, prof
   multi-cycles OK.
5. ✅ **Bulletins** : `bulletins_views.py::bulletins_main` (+ `_school_overview`) onglets et
   vue d'ensemble scopés au cycle de la période ; `students/views.py` (`student_notes_period`
   par cycle de l'élève, `_difficulty_flagged` agrège les moyennes sur la période active de
   CHAQUE cycle). Testé rollback (overview compo = 1er cycle, notes élève par cycle, suivi OK).
6. ✅ **Portail parent** (`apps/parent/views.py`) : `parent_scolarite` sélecteur de période par
   cycle de l'enfant actif ; `parent_dashboard::_cur_period` mis en cache par CLASSE (donc par
   cycle) au lieu de par école. Checks de dates null-safe. Testé rollback (scolarité enfant
   1er cycle = compositions).
7. ✅ **Dashboard directeur** (`apps/dashboard/views.py`) : `_compute_kpis` / `_compute_class_health`
   / `_compute_todo` agrègent sur la période active de CHAQUE cycle (`period__in`) ; `_compute_deltas`
   et `total_collected` rendus null-safe (dates optionnelles). **Finances** (`finance/services.py`) :
   échéancier scopé au cycle de la classe + `_due_dates_for_year` null-safe (repli segments). Promoteur = 0 site.
8. ✅ **Test complet** : chaque lot vérifié en rollback sur Sundiata (2 cycles) — grille compo = 1er
   cycle, bulletins/parent/dashboard/finances OK, non-régression périodes « sans cycle ».

---
**ÉTAPE A TERMINÉE** — config par cycle + branchement complet (saisie, bulletins, parent, dashboard, finances).

**ÉTAPE B TERMINÉE** — surcharge par classe (résolution **classe → cycle → école**). `Period.school_class`
(migration 0025) ; résolveur `periods_for_class` teste la classe d'abord (`periods_for_cycle` exclut les
périodes de classe) ; config UI « Classes personnalisées » (générer par classe + « Revenir au cycle » avec
confirmation + garde-fou notes, vue `period_class_reset`) ; onglets notes/bulletins école excluent les
périodes de classe. Testé rollback + live sur Sundiata. Les écrans par élève/classe (saisie, bulletins,
parent, finances) respectent la surcharge automatiquement via le résolveur.

Reste : **Chantier 2 (passage d'année)** — post-démo.

## Fichiers impactés (audit COMPLET vérifié après Lot 4)
Faits : `apps/schools/settings_views.py`, `apps/schools/notes_views.py`,
`apps/teachers/views.py` (+ nouveau `apps/schools/periods.py`).

Restants :
- **Lot 5 Bulletins** : `apps/schools/bulletins_views.py` (77, 730) ·
  `apps/students/views.py` (détail élève : 487, 489, 1165-66)
- **Lot 6 Parent** : `apps/parent/views.py` (68, 278)
- **Lot 7 Dashboard directeur** : `apps/dashboard/views.py` (33, 57-59, 476)
- **Finances** (échéancier) : `apps/finance/services.py` (110, 242)
- **Promoteur** : 0 site — lit les bulletins publiés, pas les périodes. ✅

`apps/schools/models.py:260` = `self.periods.count()` (propriété, inoffensif).

## Points de vigilance
- Router **tous** les `Period.objects.filter(...)` par le résolveur (sinon incohérences).
- `finance/services.py` génère les échéances de scolarité à partir des périodes
  (`_due_dates_for_year`) → vérifier qu'un cycle en compositions produit un échéancier cohérent.
- Bulletins PDF déjà générés restent valides (rattachés à leur période).

## Hors périmètre (= Chantier 2, après la démo)
- **Passage d'année / promotion N+1** (l'infra `StudentEnrollment` existe, le flux non).
- **Grille fine par classe** (6ème hybride, 7-9ème à 2/3 trimestres) — extension additive.
- **Supérieur / LMD** (crédits, UE, compensation 10/20) — modèle distinct ; l'app reste K-12.

## Plan de test (école « Groupe SyDev »)
1. Créer des classes des 2 cycles.
2. Configurer : 1er cycle = 4 compositions, 2nd cycle = 3 trimestres.
3. Vérifier saisie des notes → bonnes périodes par classe.
4. Vérifier bulletins → par cycle.
5. Vérifier Scolarité parent → périodes du cycle de l'enfant.
6. Vérifier académique promoteur → agrégats corrects.
7. **Non-régression** : une école aux périodes sans cycle fonctionne comme avant.
