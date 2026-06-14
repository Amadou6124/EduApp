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
- [ ] EmployeeProfile (Membership OneToOne)
      type: permanent/vacataire
      salary ou hourly_rate
      hire_date, is_active

- [ ] TeacherAttendance (émargement prof)
      teacher, school, class_subject
      date, status, signed_at
      recorded_by (jamais le prof lui-même)
      SÉPARÉ de Attendance élèves

- [ ] ExpenseCategory (catégories dépenses)
      name, icon, is_default
      school FK (null = globale)

- [ ] Expense (dépense école)
      school, category, amount
      date, description
      paid_by, payment_method
      is_cancelled

- [ ] SalaryPayment (paiement paie)
      employee (Membership PROTECT)
      school, year, month
      amount, hours (vacataire nullable)
      hourly_rate (snapshot)
      status: paid/pending
      payment_method, paid_at
      paid_by, employee_name (snapshot)
      is_cancelled

### Champ nouveau sur ClassSubject
- [ ] duration_hours DecimalField(2,1)
      default=2.0
      (durée d'un cours en heures)

### Champ nouveau sur School
- [ ] accounting_enabled BooleanField
      default=False
      (activer le module par école)

### Nouvelle permission StaffPermission
- [ ] can_manage_accounting BooleanField
      default=False

### App apps/accounting/
- [ ] __init__.py
- [ ] apps.py
- [ ] models.py
- [ ] services.py (compute_monthly_balance,
      compute_teacher_hours)
- [ ] views.py
- [ ] urls.py

## Phases

### PHASE 1 — Fondation
Statut : 🔄 En cours
- [ ] Créer apps/accounting/
- [ ] Modèles + migrations
- [ ] accounting_enabled sur School
- [ ] can_manage_accounting sur StaffPermission
- [ ] duration_hours sur ClassSubject
- [ ] INSTALLED_APPS + URLs

### PHASE 2 — Profils employés
Statut : ⏳ En attente Phase 1
- [ ] Section Rémunération dans /team/<id>/
- [ ] EmployeeProfile create/edit via HTMX
- [ ] Vue liste employés /accounting/staff/

### PHASE 3 — Émargement professeurs
Statut : ⏳ En attente Phase 2
- [ ] Interface émargement /accounting/emargement/
- [ ] Enregistrement par secrétaire/admin
- [ ] Vue par jour et par classe
- [ ] Calcul automatique heures vacataires

### PHASE 4 — Paie mensuelle
Statut : ⏳ En attente Phase 3
- [ ] Page paie mensuelle /accounting/salaires/
- [ ] Permanents : 1 clic payer
- [ ] Vacataires : heures auto + validation
- [ ] Fiche de paie PDF
- [ ] Historique par employé

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
(mis à jour à chaque commit)
