# Feuille de route post-démo — EduApp

Produit **K-12 pour le Mali** (Fondamental + Secondaire). Le supérieur (LMD) est **hors périmètre** assumé.
Cette feuille de route liste ce qui reste à construire, priorisé, après la première démo directeur.

> ## ⚠️ PRINCIPE — ne pas se noyer avant le lancement
> **Avant de déployer, on ne construit QUE ce qui bloque le déploiement ou la vraie utilisation.**
> Tout le reste (automatisations, cas avancés, confort) = **APRÈS lancement**. L'ordre de mise en
> production est dans [go-live-checklist.md](go-live-checklist.md) — c'est **lui** qui pilote, pas
> l'envie d'ajouter des fonctionnalités. Un enrichissement qui n'empêche pas une école d'utiliser
> l'app au quotidien peut attendre.

---

## ✅ Fait

### Périodes par cycle (A+B) — **mergé dans `main`**
- **Périodes par cycle (Étape A)** : compositions au fondamental / trimestres au secondaire dans la
  même année ; dates optionnelles (`is_notes_open` pilote le réel) ; résolveur central
  `apps/schools/periods.py` ; branché notes, bulletins, parent, dashboard, finances.
- **Surcharge par classe (Étape B)** : une classe peut sortir de son cycle (`Period.school_class`) ;
  résolution **classe → cycle → école** ; UI « personnaliser une classe » + « revenir au cycle ».
- **Tranches auto-provisionnées** : 3 gabarits (Annuel/Trimestriel/Mensuel, Trimestriel défaut).
- **Écran années peaufiné** + fix dashboard + wording « Tranches → Échéances ».

### Fiabilisation + dossier élève + remises — **mergé dans `main`**
- **68 tests + sécurité + base propre** : isolation multi-écoles, chemins argent, notes→bulletins,
  rate-limiting login fiabilisé. Recette prod vierge : `ouvrir-prod-vierge.md`.
- **Identité élève** : Nom/Prénom séparés, lieu + date de naissance, **matricule** auto (AAAA-NNNN, immuable, modifiable).
- **Responsables** (`StudentGuardian` unifié) : info seule OU accès portail ; téléphone élève retiré (donnée morte).
- **Remises manuelles** (`FeeAdjustment`) : % ou montant, motif, financé par, **immuable** ; garde-fou anti
  trop-perçu ; **reporting** directeur + promoteur ; solde **net** partout. (Auth élève/parent = analysé, pas construit → `decision-authentification.md`.)

### Ciblage des frais par niveau + polish — branche `feature/chantiers-suivants` (poussée, à merger)
- **Ciblage des frais par niveau** (`FeeType.applies_to_levels`) : un frais annexe cible certains niveaux
  (vide = tous, rétro-compatible) ; `is_applicable()` combine niveau ET nouveau/ancien ; non-rétroactif ;
  cases à cocher + badge + options d'inscription filtrées par classe. 72 tests.
- Retrait de l'avatar redondant sur l'accueil enseignant.

---

## 🔴 Essentiel (le produit le réclame)

### Passage d'année (Chantier 2)
L'infra existe (`StudentEnrollment` est par année, statut `Passé/Diplômé`) mais **le flux de promotion
N+1 n'est pas construit**. Sans lui, impossible d'« avancer » proprement d'une année à l'autre.
- Promouvoir chaque inscription ACTIVE → classe supérieure (ou Diplômé pour la dernière), figer l'ancienne.
- Créer l'année N+1 + ses périodes, reporter les soldes impayés (⚠ les frais ne sont pas rattachés à l'année).
- Gros flux à haut risque → à faire proprement (maquette → validation → code → test).
- *Ne mord qu'à la bascule (juin) → à finir avant, mais ne bloque pas le premier déploiement.*

---

## ⏸️ APRÈS LANCEMENT (enrichissements — ne pas s'y noyer avant)

Ces chantiers **n'empêchent pas** une école d'utiliser l'app au quotidien. On les prend **après** que
l'app tourne en vrai, école par école, selon la demande réelle.

### Remises — niveau 2 (le niveau 1 manuel est fait et suffit pour ouvrir)
6 briques **indépendantes**, à activer une par une si le besoin vient :
- **Fratrie automatique** : détecter les frères/sœurs (responsables partagés) + appliquer la remise
  auto (2ᵉ enfant −X %…) + recalcul dynamique. *Risque argent → à faire prudemment.*
- **Avoirs / remboursements** : au lieu de refuser un trop-perçu, créer un crédit (remboursable / reportable).
- **Validation à deux** : le caissier propose, le directeur approuve (états brouillon/approuvé). *Grandes écoles.*
- **Plafond de cumul** : limite max de remise par élève (ex. 30 %).
- **Motifs configurables** par école (aujourd'hui « Autre + justification » suffit).
- **Pénalités de retard** : l'inverse d'une remise. *Le modèle est déjà prêt (`FeeAdjustment.type`) → le plus rapide.*

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
  (inscription, tenue) = **1 échéance** chacun. Ciblage sur **2 axes** (ET) : nouveau/ancien (`applies_to`)
  **et niveau** (`applies_to_levels`, **vide = tous**) — via `FeeType.is_applicable(classe, is_returning)`.
- **Élève actif** : `Student.is_active` est un **CACHE** qui doit rester cohérent avec le statut de
  l'inscription (`StudentEnrollment.status`). **On ne le mute JAMAIS à la main** — uniquement via
  `Student.archive(status)` / `Student.reactivate()` (atomiques, seules autorisées). Sinon le flag et le
  statut divergent (= le bug 500 d'archivage réparé). « Revient l'année suivante » = **ré-inscription**
  (nouvelle année), pas une réactivation. Matières : couleur **auto distincte** (`pick_subject_color`, pas de
  choix manuel → pas de collision).
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
> Audité juillet 2026 : **`brand-blue → primary` FAIT** (focus ring restauré, 4 fichiers) ;
> **alerte émargement** et **`components.css` orphelin** = déjà faits/inexistants (retirés).
- **Réactivation d'un élève archivé** (onglet « Archivés » + bouton, comme la réactivation équipe). *Petit, après lancement.*
- **Migration Lucide 1.20.0 → 0.5xx** (chore ; les noms d'icônes changent → audit avant). *Non urgent, après lancement.*
- Cosmétiques divers : carte dashboard demi-largeur, erreurs Alpine console, labels de groupe HTMX orphelins (notifications).

*(Déjà faits, donc retirés du backlog : catalogue de frais + échéancier par tranches, liste rouge des impayés,
portail parent financier, périodes par cycle.)*
