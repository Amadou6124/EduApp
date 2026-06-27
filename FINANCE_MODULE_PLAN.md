# Module Finances — Plan & Évolution

Branche : `feature/finance-module` (depuis `develop`)
Dernière mise à jour : 2026-06-27 — Lot 1 terminé

## Objectif
Refonte du système de frais, tranches de paiement et inscription annuelle pour EduApp.
Trois problèmes identifiés :
1. **Frais rigides** — frais liés à la classe globale, pas modulaires par élève (genre, cantine, transport, remises impossibles).
2. **Aucune dimension temporelle** — paiement = simple compteur, sans dates d'exigibilité ni tranches réelles.
3. **Pas de colonne vertébrale annuelle** — `Student.school_class` est l'unique vérité « présent éternel » ; `StudentEnrollment` inerte ; pas de réinscription.

## Principes directeurs
- Migrations **additives uniquement** (champs nullable ou défauts, jamais de rupture).
- `Payment` reste un **journal de transactions immuable** — on n'y touche pas ; l'allocation se fait via une table dédiée.
- Le solde se **calcule**, ne se stocke jamais en champ muté.
- Frais accrochés à l'**année scolaire** (via `StudentEnrollment`), pas au `Student` directement.
- Modèle « défaut + exception » : config école héritée par toutes les classes, surchargeable au cas par cas.

## Architecture cible (modèle de données)
- **Catalogue de frais** (niveau école) : type, montant, obligatoire/optionnel, périodicité, variantes.
- **Variantes de frais** : tenue (fille/garçon, auto par genre), bus (par trajet), cantine (par formule).
- **Fiche financière élève** : postes dus par élève, accrochés à l'enrollment de l'année.
- **Échéancier** : lignes datées (montant attendu, date limite, statut), générées par un gabarit.
- **Allocation de paiement** : table liant `Payment` ↔ échéance(s), avec montant ventilé.
- **Gabarits de tranches** (niveau école) : annuel / trimestriel / mensuel, surchargeable par élève.

## Lots d'exécution
- [x] **Lot 1 — Socle temporel** : réveiller `StudentEnrollment` (source de vérité, contrainte unique `(élève, année)`, statut `ACTIVE` écrit) + champ genre sur `Student`. Modèles + migration, sans UI.
- [ ] **Lot 2 — Catalogue de frais** : modèles catalogue + variantes + écran de config école.
- [ ] **Lot 3 — Fiche financière par année** : postes élève + échéancier + allocation, liés à l'enrollment actif.
- [ ] **Lot 4 — Inscription enrichie** : flux 3 clics générant la fiche financière à l'inscription.
- [ ] **Lot 5 — Encaissement + timeline** : écran de paiement au guichet (timeline de tranches colorées).
- [ ] **Lot 6 — Tableau de bord impayés** : liste rouge filtrée par date d'échéance.
- [ ] **Lot 7 — Passage de classe** : flux de fin d'année (régénération fiche année N+1) — boucle et valide l'architecture annuelle.

## Décisions actées
- Bus/cantine = **abonnements** mensuels résiliables ou forfait annuel, **pas** des tranches de scolarité.
- Frais à **variantes** (un concept unique couvre tenue, bus, cantine).
- Scolarité reste **par classe** (`SchoolClass.annual_fee`), découpée par gabarit.
- Inscription = frais ponctuel annuel, règle « nouveaux / anciens » configurable au niveau école.
- Passage de classe construit **maintenant** (lot 7) pour valider l'architecture, pas reporté.

## Points de vigilance (relevés aux audits)
- Incohérence charte : `brand-blue` (components.css) vs `primary-600/700` (templates) — trancher la couleur officielle.
- Bug latent fiche élève : template référence `payment.is_valid` / `payment.paid_at`, champs absents du modèle (`is_cancelled`, `payment_date`). À corriger en passant (lot 5).
- Import 1000 élèves synchrone + sérialisation DOM — à valider en charge.
- `School.current_school_year` (CharField décoratif) coexiste avec `SchoolYear.is_active` (structurant) — ne pas confondre.
- `StudentEnrollment` sans contrainte d'unicité aujourd'hui — à ajouter au lot 1.

## Journal des sessions
| Date | Lot | Ce qui a été fait |
|------|-----|-------------------|
| 2026-06-27 | — | Création branche + plan initial |
| 2026-06-27 | 1 | Champ `Student.gender` (M/F, nullable) + `Gender` TextChoices. Contrainte unique conditionnelle `uniq_enrollment_student_year` sur `StudentEnrollment (student, school_year)` (condition `school_year__isnull=False`). Docstring « source de vérité » sur le modèle. Migration schéma `0006` + data migration `0007` (backfill enrollments ACTIVE des élèves actifs vers l'année active, idempotente, reverse no-op). Backfill vérifié : 1074/1074 élèves rattachés, 0 doublon, école sans année active ignorée. Aucune UI touchée. |
