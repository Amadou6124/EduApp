# Chantier — Passage d'année scolaire (« lot 7 »)

> Document de planification. Aucun code ici. À affiner avant chaque sous-lot.
> Issu de l'audit lecture seule réalisé sur `feature/finance-module` (2026-06-28).

---

## 1. Contexte & ampleur

Le « lot 7 » n'est **pas un lot** : c'est un **chantier** — la transition complète d'une année scolaire à la suivante. Il dépasse largement les finances : il touche **élèves, notes, bulletins, finances, classes, inscriptions, redoublants, sortants, archivage**.

**Estimation honnête : 4 à 5 sous-lots** (cf. §5), et non un lot unique.

**Pré-requis de planning :**
- À faire **APRÈS le merge du module finance** (`feature/finance-module` → `develop`/`main`).
- Sur une **nouvelle branche dédiée, partie de `develop`** (pas sur la branche finance).
- Ce document est commité **sur `feature/finance-module`, avant le merge**, comme mémoire du chantier à venir.

---

## 2. La carte du territoire (audit)

### 2.1 Modèle d'année

**`SchoolYear`** (`apps/schools/models.py`) : `school` (FK), `name` (« 2024-2025 »), `start_date`, `end_date`, `is_active`, `created_at`. Ordering `-start_date`.

**`StudentEnrollment`** (`apps/students/models.py:211`) — **conçu pour ce chantier** (la docstring dit : « Le passage de classe (lot 7) créera l'enrollment de N+1 ») :
- Champs : `student` (PROTECT), `school` (PROTECT), `school_class` (PROTECT), `school_year` (PROTECT, **nullable** pour archives legacy), `status`, `enrolled_at`, `ended_at`.
- **Statuts** (`EnrollmentStatus`) : `ACTIVE`, `TRANSFERRED`, `GRADUATED`, `WITHDRAWN`. **Pas de statut REDOUBLANT.**
- **Un seul enrollment par (élève, année)** : `UniqueConstraint(['student','school_year'], condition=school_year__isnull=False)`. Les archives sans année (legacy) ne sont pas contraintes.

**Détermination de « l'année active »** : **aucun helper central**. Le pattern `SchoolYear.objects.filter(school=…, is_active=True).first()` est répété **en dur dans ~12 fichiers** (dashboard, teachers, context_processors, students, receipt_generator, notes, bulletins…), avec des **fallbacks incohérents** (certains retombent sur `order_by('-start_date').first()`, d'autres sur `None`).

### 2.2 Inventaire des dépendances temporelles

Pour chaque domaine : la donnée est-elle liée à l'**année**, à la **date**, ou **permanente** ? Crucial pour savoir ce qui s'archive / se régénère / se reporte.

| Domaine | Rattaché à | Détail (chemin) |
|---|---|---|
| **Élève (identité)** | **Permanent** | `Student` n'a **pas** de `school_year`. `school_class` = **FK DIRECTE** = « éternel présent » / cache de l'enrollment courant. Permanents : identité, `access_code`, `is_active`, **gamification** (`total_xp`, `current_level`, `streak_days`, `badges`). `tuition_fee` = **une seule valeur** (pas d'historique par année). |
| **Notes** | **Année via `Period`** | `Note` → `student` + `class_subject` + `period` (`schools/models.py:415`). Année = `period.school_year`. Liées au **Student direct**, pas à l'enrollment. |
| **Bulletins** | **Année via `Period` + classe figée** | `Bulletin` → `student` + `period` + `school_class` (**snapshot**) (`schools/models.py:628`), `unique(student, period)`. La classe figée → l'historique survit au changement de classe. |
| **Finances** | **Année via `enrollment`** ✅ | `StudentFeeAccount` = **OneToOne `enrollment`** (`finance/models.py`) : « un account par enrollment, l'historique des années passées reste intact ». `FeeDebt`/`Installment`/`PaymentAllocation` en cascade. Le **`Payment` est rattaché au `Student` direct** ; l'allocation fait le pont vers la tranche/année. |
| **Absences** | **Date (pas de FK année)** | `Attendance` → `student` + `school_class` (snapshot) + `date` (`teachers/models.py:15`). Année **implicite via la date**. |
| **Observations** | **Permanent (flux élève)** | `StudentObservation` → `student` + `created_at`, **ni année ni classe** (`teachers/models.py:87`). |
| **Classes** | **Permanent (réutilisé)** | `SchoolClass` = **pas de `school_year`** (`schools/models.py:118`). La même « 10ème Année » persiste. `annual_fee` = valeur courante unique. `ClassSubject` (coefficients/matières) et `Subject` **permanents**. |
| **Périodes** | **Année** | `Period` → `school_year` (`schools/models.py:254`), `unique(school_year, name)`. |

**Effectifs de classe** = comptés sur la **FK directe** : `sc.students.filter(is_active=True).count()` (`dashboard/views.py:171,283`, `teachers/views.py:119,222`). Un effectif reflète **toujours l'année courante uniquement** ; le roster historique n'est récupérable que depuis les enrollments/bulletins, pas depuis la classe.

### 2.3 Ce qui existe vs ce qui manque

**Existe :**
- Gestion des années : liste, création, édition, **toggle activer/archiver** (`schools/settings_views.py:243-333`). Activer = **simple bascule de flag, sans migration de données**.
- `student_archive` (sortie individuelle : transfert/abandon/diplômé) (`students/views.py:524`).
- `is_returning_student(enrollment)` (`finance/services.py:34`) : distingue ANCIEN/NOUVEAU pour le **tarif** des frais (graine de la réinscription).
- Notes & bulletins **déjà multi-années** : sélecteur `?year=` + repli (`notes_views.py:33,156`, `bulletins_views.py:62`).
- Inscription (lot 4a) + import (lot 4b) créent l'enrollment de l'année active via `ensure_active_enrollment` (`students/services.py`).

**Manque :** tout flux de transition **collectif** (promotion en masse, réinscription en masse, clôture d'année), toute notion de **report de solde**, tout **statut redoublant**, toute action « passer à l'année suivante ».

---

## 3. Les pièges identifiés (critique — à traiter en priorité)

- 🔴 **Double comptage financier.** Le scope financier filtre `enrollment__status='active'` + `student.is_active`, **jamais `school_year`** (`fee_accounts_annotated`, `finance/services.py`). Tant qu'il n'y a qu'une année, `status='active'` ≈ année courante. Dès qu'un élève a un enrollment **actif** N **et** N+1, les **deux fiches** sont comptées → agrégats finance (dashboard, promoteur, page Paiements) **doublés**. **À CORRIGER avant toute création d'enrollment N+1.** Aggravant : **rien ne fige automatiquement l'enrollment N** en statut terminal (aucun passage à TRANSFERRED/GRADUATED hors `student_archive` manuel).

- 🔴 **`student_archive` crée un enrollment** `(student, active_year)` (`students/views.py:553`). Si l'élève a **déjà** un enrollment ACTIVE pour cette année (cas normal post-lot 4), c'est une **violation de la contrainte unique** `uniq_enrollment_student_year`. Latent aujourd'hui (élèves legacy sans enrollment), piège direct dès que tout le monde a un enrollment.

- 🔴 **Discordance contrainte / règle « une seule année active ».** La règle est tenue **seulement au niveau applicatif** (`SchoolYear.clean()` / `full_clean()`), **pas en base** : la contrainte DB réelle est `UniqueConstraint(['school','name'], condition=is_active=True)` — elle empêche deux années **de même nom** actives, pas deux années **différentes** actives. Un `save()`/`update()` contournant `clean()` peut créer 2 années actives.

- 🟠 **`Student.school_class` est le seul pointeur « présent » écrasable.** Une promotion en masse le réécrirait. S'il est mal fait, on perd le « où en est l'élève maintenant ». L'historique (notes, bulletins, fiches) survit (ancré sur period/enrollment) — mais ce cache courant n'a **aucun filet**.

- 🟠 **Fenêtre « zéro année active ».** Activer N+1 impose d'**archiver N d'abord** (le toggle refuse 2 actives). Entre les deux : zéro année active → l'inscription est **bloquée** (`has_active_year`) et tous les `…filter(is_active=True).first()` renvoient `None`.

- 🟠 **Pas de résolveur d'année central** (cf. §2.1) : pattern répété en dur (~12 fichiers), fallbacks incohérents → comportements divergents si 0 ou 2 années.

- **Irréversibilité.** Aucune transaction de transition réversible n'existe. Une promotion en masse sur 244 élèves doit être pensée annulable.

**Note rassurante :** par conception, **aucune donnée historique n'est perdue** par un passage d'année correct — notes (period), bulletins (period + classe figée), fiches (enrollment), absences (date), observations (flux) sont ancrées hors du « présent ». Le seul point fragile est `Student.school_class`.

---

## 4. Décisions métier à trancher (à lister — NE PAS résoudre ici)

1. **Solde impayé de fin d'année** : reporté en dette N+1 / bloque la réinscription / abandonné / archivé tel quel ?
2. **Redoublant** : statut dédié ? garde ses notes (oui par conception) ? tarif différent ?
3. **Promotion** : automatique (par ordre de niveaux) ou manuelle classe par classe ? Réversible ?
4. **Réinscription** : opt-in (l'élève doit être ré-inscrit) ou tous reconduits par défaut sauf sortants ?
5. **Sortants / diplômés** : détection auto (niveau terminal) ou marquage manuel ?
6. **Bascule d'année** : qui la déclenche (directeur / promoteur), et que fait-on de la fenêtre « zéro année active » ?
7. **Archivage** : figé (lecture seule) ou consultation en place via les sélecteurs d'année existants ?
8. **`student.tuition_fee` unique** : conserver (legacy) ou basculer sur l'`annual_fee` de la classe par année ?

---

## 5. Découpage proposé en sous-lots (plan de travail provisoire)

> Ordre **dicté par le risque** — à affiner avant chaque sous-lot.

- **7-A — Fondation année** : résolveur d'année central + **scope financier par année** (corriger le double comptage) + fix du piège `student_archive` / contrainte unique + discordance « une seule année active ». **PRÉALABLE OBLIGATOIRE.**
- **7-B — Transition d'un élève** : promotion / redoublement / sortie, **un par un**, réversible (réutilise enrollment + repointage `Student.school_class`).
- **7-C — Transition en masse** : promotion / réinscription collective d'une classe ou de l'école, création des fiches N+1.
- **7-D — Solde reporté** : politique du dû impayé en fin d'année (cf. décision §4.1).
- **7-E — Clôture / bascule d'année** : activation N+1 atomique (gérer la fenêtre « zéro année active ») + périodes N+1 + écrans historiques.

**Impératif d'ordre : 7-A en premier.** Tant que la finance scope par `status` et non par année, **créer le moindre enrollment N+1 fausse tous les chiffres finance** déjà unifiés au lot 6bis.

---

## 6. Journal des sous-lots

| Date | Sous-lot | Ce qui a été fait |
|------|----------|-------------------|
| _(vide — à remplir au fil du chantier)_ | | |
