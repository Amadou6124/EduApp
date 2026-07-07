# Feuille de route post-démo — EduApp

Produit **K-12 pour le Mali** (Fondamental + Secondaire). Le supérieur (LMD) est **hors périmètre** assumé.
Cette feuille de route liste ce qui reste à construire, priorisé, après la première démo directeur.

---

## ✅ Fait (session « périodes par cycle » — branche `feature/periodes-par-cycle`)

- **Périodes par cycle (Étape A)** : compositions au fondamental / trimestres au secondaire dans la
  même année ; dates optionnelles (`is_notes_open` pilote le réel) ; résolveur central
  `apps/schools/periods.py` ; branché notes, bulletins, parent, dashboard, finances.
- **Surcharge par classe (Étape B)** : une classe peut sortir de son cycle (`Period.school_class`) ;
  résolution **classe → cycle → école** ; UI « personnaliser une classe » + « revenir au cycle ».
- **Tranches auto-provisionnées** : 3 gabarits (Annuel/Trimestriel/Mensuel, Trimestriel défaut) créés
  automatiquement pour toute école (`ensure_default_schedule_templates`).
- **Écran années peaufiné** : rappel école/année, archivage rassurant, suppression réservée aux années vides.
- **Fix dashboard** (crash date `H:i`) + **wording** « Tranches → Échéances » (onglet En retard).

---

## 🔴 Essentiel (le produit le réclame)

### 1. Passage d'année (Chantier 2)
L'infra existe (`StudentEnrollment` est par année, statut `Passé/Diplômé`) mais **le flux de promotion
N+1 n'est pas construit**. Sans lui, impossible d'« avancer » proprement d'une année à l'autre.
- Promouvoir chaque inscription ACTIVE → classe supérieure (ou Diplômé pour la dernière), figer l'ancienne.
- Créer l'année N+1 + ses périodes, reporter les soldes impayés (⚠ les frais ne sont pas rattachés à l'année).
- Gros flux à haut risque → à faire proprement (maquette → validation → code → test).

### 2. Ciblage des frais par cycle/niveau
Aujourd'hui « obligatoire = tout le monde » (seule distinction : nouveau/ancien). Résultat : « Inscription
préscolaire » tombe sur une 1ère année. **Plan déjà écrit** (même schéma que les périodes) :
- `FeeType.applies_to_levels` (vide = tous, rétro-compatible) ; filtre à la génération des frais ; UI
  « niveaux concernés » + badge dans le catalogue.
- *NB : la scolarité est déjà par classe (montants variables par niveau OK) — ce chantier concerne les frais annexes.*

---

## 🟠 Important (réalisme terrain)

### 3. Module Emploi du temps (n'existe pas)
Aucun planning « qui enseigne quoi, quel jour, quelle heure ». **Pas nécessaire pour la paie** (l'émargement
capte les heures réelles variables — ex. Lundi 3h / Jeudi 2h fonctionne), mais un vrai directeur veut planifier
et afficher un emploi du temps hebdomadaire. Module à part entière.

### 4. Vue / fiche « enseignant » + fil vers la rémunération
Les heures d'un prof sont **dispersées** (une `duration_hours` par class-matière, défaut 2h) — aucune vue
unique « ses cours, ses heures ». Et **3 écrans non reliés** : créer le prof (Équipe) → l'assigner (Paramètres)
→ régler sa paie (Comptabilité). Un directeur ne devine pas le 3ème. Améliorer la découvrabilité + une fiche prof.

---

## 🟢 Confort (petits polish)

5. **Nombre de tranches libre** (2/4/6…) — actuellement figé à 1/3/9.
6. **Cosmétique matières** — collision de couleur auto entre 2 matières ; abréviation affichée trop pâle.
7. **Frais de démo** — le bouton « Charger un exemple » ajoute des frais à nettoyer sur une vraie école.

---

## 🧭 Rappels de modèle (pour ne pas se re-tromper)

- **École (persistant, réutilisé chaque année)** : classes, frais (catalogue + gabarits), matières, élèves.
- **Année (archivé avec elle)** : périodes, inscriptions, notes, bulletins.
- **Frais** : scolarité **par classe** (`annual_fee`) découpée en tranches (gabarit 1/3/9) ; frais ponctuels
  (inscription, tenue) = **1 échéance** chacun ; **pas de ciblage par niveau** (cf. 🔴 #2).
- **Matière** = catalogue (nom/abréviation/couleur). **Classe-matière** = coefficient (déf. 1.0), note max
  (déf. 20), **durée d'un cours** (déf. 2h), enseignant — **tout par classe, libre**.
- **Heures prof** = par cours (durée) + **émargement** (heures réelles). **Pas** de volume horaire au niveau prof,
  **pas** d'emploi du temps.
- **Paie** (Comptabilité) : Permanent (salaire fixe) ou Vacataire (taux horaire, variable par cours) ;
  paie vacataire = Σ heures émargées × taux.

---

## 📥 Backlog produit (consolidé depuis les anciens `TODO.md` + `NOTES_TECHNIQUES.md`)

> Items hérités des notes de développement. Certains peuvent être **partiellement faits** —
> à re-vérifier au moment de les prendre. Regroupés ici pour avoir **une seule source de vérité**.

### Fonctionnalités demandées (haute → moyenne)
- **Demande de RDV parent → directeur** (modèle `MeetingRequest` : soumettre côté parent, gérer côté admin, notif directeur). *Priorité haute.*
- **Page « Toutes mes observations »** (portail enseignant) — aujourd'hui le prof ne voit que ses 5 dernières. *Priorité haute.*
- **Justification d'absence par le parent** (modèle `AbsenceJustification` : soumettre + valider/refuser). *Moyenne.*
- **Caisse journalière** (`/accounting/caisse/`) — journal du jour, solde ouverture/clôture, « clôturer la journée ». *~3 j.*
- **Certificats & attestations PDF** (scolarité, présence, radiation, transfert) avec en-tête + photo + signature. *~2 j.*
- **Dossier élève — pièces jointes** (extrait de naissance, vaccins, photo) + indicateur complet/incomplet. *~3 j.*
- **Messagerie bidirectionnelle parent ↔ école** (badge non-lu des deux côtés). *~4 j.*
- **Bilan annuel consolidé** (P&L sur l'année + export PDF propriétaire). *~2 j.*
- **Relances automatiques impayés** (SMS J+5 / J+15) — le bouton « Relancer » est aujourd'hui un **placeholder**.
- **Restes du chantier multi-école** : portail parent multi-école + **transfert d'élève entre écoles** (historique préservé).

### Dette technique / polish
- **`forms.py` : `brand-blue` → `primary`** (focus ring perdu depuis la refonte design) — `accounts/team_forms.py`, `accounts/forms.py`, `payments/forms.py`, `schools/forms.py`.
- **Réactivation d'un élève archivé** (onglet « Archivés » + bouton, équivalent de la réactivation équipe déjà faite).
- **Alerte émargement dashboard** (profs attendus vs émargés du jour).
- **Migration Lucide 1.20.0 → 0.577.x** (chore ; audit des noms d'icônes avant).
- **Nettoyage `components.css` orphelin** (`brand-blue` hors build).
- Cosmétiques divers : carte dashboard restée en demi-largeur, erreurs Alpine console, labels de groupe HTMX orphelins (notifications).

*(Déjà faits, donc retirés du backlog : catalogue de frais + échéancier par tranches, liste rouge des impayés,
portail parent financier, périodes par cycle.)*
