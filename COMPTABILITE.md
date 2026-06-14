# Module Comptabilité EduApp

## Objectif
Gérer la paie du personnel et les
dépenses des écoles privées maliennes.

## Types d'employés couverts
- Enseignants permanents (salaire fixe)
- Enseignants vacataires (à l'heure)
- Staff administratif (secrétaire,
  comptable, censeur, surveillant)
- Staff de soutien (gardien, agent
  d'entretien, cuisinier, chauffeur)

## Architecture décidée

### Nouveaux modèles (apps/accounting/)
- [x] EmployeeProfile (Membership OneToOne PROTECT)
      type: permanent/vacataire ; monthly_salary / hourly_rate ; hire_date ; is_active
- [x] TeacherAttendance (émargement prof) — SÉPARÉ de Attendance élèves
      teacher, school, class_subject, date, status (present/absent/replaced),
      substitute (FK User), signed_at, recorded_by, note
      → UniqueConstraint(class_subject, date)
- [x] ExpenseCategory (school FK null=globale, name, icon, is_default, is_active)
- [x] Expense (school, category PROTECT, amount, date, description, payment_method, paid_by, is_cancelled)
- [x] SalaryPayment (employee=Membership PROTECT, school, year, month, amount,
      hours, hourly_rate snapshot, status paid/pending, payment_method, paid_at,
      paid_by, employee_name snapshot, is_cancelled)
      → UniqueConstraint(employee, year, month) WHERE not cancelled (1 paie/mois V1)

### Champ nouveau sur ClassSubject
- [x] duration_hours DecimalField(max_digits=3, decimal_places=1) default=2.0

### Champ nouveau sur School
- [x] accounting_enabled BooleanField default=False

### Nouvelle permission StaffPermission
- [x] can_manage_accounting BooleanField default=False (+ dans preset_comptable)

### App apps/accounting/
- [x] __init__.py
- [x] apps.py
- [x] models.py
- [ ] services.py (compute_monthly_balance, compute_teacher_hours) — Phase 6
- [x] views.py (vide, Phases 2-7)
- [x] urls.py (vide, routes Phase 2+)

## Phases

### PHASE 1 — Fondation
Statut : ✅ Terminée (migrations appliquées, check OK)
- [x] Créer apps/accounting/
- [x] Modèles + migrations
- [x] accounting_enabled sur School
- [x] can_manage_accounting sur StaffPermission
- [x] duration_hours sur ClassSubject
- [x] INSTALLED_APPS (URLs config à câbler en Phase 2 — routes vides pour l'instant)

Migrations (ordre strict schools → accounts → accounting) :
- `schools/0013_add_duration_hours_accounting_enabled.py`
- `accounts/0005_add_can_manage_accounting.py`
- `accounting/0001_initial_accounting_models.py`
Index/contraintes tous ≤ 30 car. (max : uniq_teacher_att_course_date = 28).

### PHASE 2 — Profils employés
Statut : ✅ Terminée
- [x] Section Rémunération dans /team/<id>/ (lazy-load HTMX, tous rôles)
- [x] EmployeeProfile create/edit via HTMX (panel + save, validation permanent/vacataire)
- [x] Décorateur director_or_accounting_required (core/mixins.py)
- [x] Gate school.accounting_enabled (template + vues 403)
- [x] Vue liste employés /accounting/staff/ (filtres Alpine, alerte sans profil, zéro N+1)
- [x] Lien sidebar Comptabilité (gate accounting_enabled + director/can_manage_accounting)

Routes : accounting:staff-list, staff-remuneration(-save). config/urls.py câblé (/accounting/).

### PHASE 3 — Émargement professeurs
Statut : 🔄 En cours
- [x] Interface émargement /accounting/emargement/ (cours groupés par classe, accordéons)
- [x] Enregistrement par secrétaire/admin (décorateur director_or_emargement_required)
- [x] Vue par jour (nav ◄ Hier / Aujourd'hui / Demain ►) et par classe
- [x] Sessions matin/après-midi/journée (2 émargements/jour possibles)
- [x] Anti-fraude : recorded_by ≠ teacher (422 si auto-émargement) + substitute search
- [x] UI optimiste (Alpine instant + fetch background, stats live)
- [x] Lien sidebar Émargement (gate accounting_enabled + can_record_emargement)
- [ ] Calcul automatique heures vacataires (Phase 4 : Σ duration_hours présents)

### PHASE 4 — Paie mensuelle
Statut : ✅ Terminée
- [x] services.py : compute_teacher_hours (FULL_DAY=2×, 2 GROUP BY), compute_monthly_salary_preview, generate_payslip_pdf
- [x] Page paie /accounting/salaires/ (2 sections permanents/vacataires, sélecteur mois, 3 cards résumé prévu/payé/attente)
- [x] Permanents : salaire fixe pré-rempli
- [x] Vacataires : heures auto (depuis émargement) × taux
- [x] Workflow 2 étapes : pay (PENDING, montant recalculé serveur + snapshots) → confirm (PAID + paid_at/by) ; cancel soft
- [x] Anti double-paiement : pré-check + IntegrityError
- [x] Fiche de paie PDF WeasyPrint (snapshots immuables)
- [x] Lien sidebar Paie mensuelle (gate accounting_enabled + can_manage_accounting)

### PHASE 5 — Dépenses
Statut : ⏳ En attente Phase 4
- [ ] Catégories prédéfinies (loyer, eau,
      électricité, fournitures, entretien,
      transport, communication, autre)
- [ ] Saisie dépense HTMX
- [ ] Liste avec filtres mois/catégorie

### PHASE 6 — Bilan financier
Statut : ⏳ En attente Phase 5
- [ ] Service compute_monthly_balance()
- [ ] Page bilan /accounting/bilan/
- [ ] Revenus (paiements élèves existants)
- [ ] Charges (salaires + dépenses)
- [ ] Résultat net
- [ ] Graphique mensuel Chart.js
- [ ] Export Excel

### PHASE 7 — Dashboard comptabilité
Statut : ⏳ En attente Phase 6
- [ ] Page principale /accounting/
- [ ] 4 KPI cards
- [ ] Graphique 6 mois
- [ ] Alertes salaires en attente
- [ ] Lien sidebar visible
  director + can_manage_accounting

## Décisions prises
- SalaryPayment.employee → Membership PROTECT
- TeacherAttendance SÉPARÉ de Attendance élèves
- Heures vacataires = auto via TeacherAttendance
  ou manuel si pas d'émargement
- ExpenseCategory : globales prédéfinies
  + possibilité école d'en ajouter
- Bilan mensuel calendaire (year, month)
  pas Period académique
- JAMAIS le prof enregistre son propre
  émargement (anti-fraude)
- can_manage_accounting pour comptable
- accounting_enabled par école (toggle)

## Anti-fraude
- TeacherAttendance.recorded_by ≠ teacher
  (vérifié côté serveur)
- Validation directeur avant paiement
- Snapshot employee_name + hourly_rate
  dans SalaryPayment (immuable après paiement)
- Soft cancel uniquement (is_cancelled)
- Timestamp signed_at automatique

## Catégories dépenses prédéfinies
- Loyer
- Électricité
- Eau
- Internet/Téléphone
- Fournitures scolaires
- Matériel de bureau
- Produits d'entretien
- Transport/Carburant
- Réparations/Maintenance
- Événements scolaires
- Frais administratifs (DNEE, etc.)
- Autre

## Règles code
- DecimalField(max_digits=12, decimal_places=0)
  partout (FCFA sans centimes)
- Isolation école : school FK sur tous modèles
- @director_or_accounting_required
  nouveau décorateur
- Zéro N+1 : agrégats GROUP BY
- Soft delete partout (is_cancelled)

## Tests obligatoires avant merge
- [ ] Isolation école (A ne voit pas B)
- [ ] Anti-fraude émargement
- [ ] Calcul heures vacataires exact
- [ ] Bilan = revenus - charges correct
- [ ] Export PDF fiche de paie
- [ ] Soft cancel sans perte données

## Commits
- `983782e` chore: COMPTABILITE.md - plan complet module comptabilité écoles maliennes
- _(à venir)_ feat: Phase 1 - fondation comptabilité (5 modèles, 3 champs, app accounting)
