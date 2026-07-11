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
  trop-perçu ; **reporting** directeur + promoteur ; solde **net** partout.

### Ciblage des frais + gabarits + auth portail — branche `feature/chantiers-suivants` (poussée, à merger)
- **Ciblage des frais par niveau** (`FeeType.applies_to_levels`) : un frais annexe cible certains niveaux
  (vide = tous, rétro-compatible) ; `is_applicable()` combine niveau ET nouveau/ancien ; non-rétroactif ;
  cases à cocher + badge + options d'inscription filtrées par classe.
- **Gabarits de tranches personnalisables** (CRUD) : le directeur crée/édite/désactive ses gabarits
  (nombre 1–12, désactivation seule, défaut protégé, non-rétroactif). Moteur de découpe inchangé.
- **Auth portail parent/élève CONSTRUIT** (Chantier B — était « analysé », `decision-authentification.md`) :
  identifiants remis via **carte imprimable** (parent au modal, élève page réimprimable), mot de passe
  temporaire **tapable** à usage unique (**changement forcé** à la 1re connexion via middleware),
  **régénération** mdp parent + code élève, **impression de masse** des cartes élève par classe (A4).
  Zéro SMS. Le portail reste un bonus, jamais un prérequis à l'inscription.
- Retrait de l'avatar redondant sur l'accueil enseignant.
- **187 tests** au total sur la branche.

---

## 🔴 Essentiel (le produit le réclame)

### Périodes personnalisées par classe dans les bulletins — décision : cycle-based (test day #5)
Constat : la page Bulletins fonctionne PAR CYCLE (Fondamental 1er = compositions, 2ème/Secondaire =
trimestres — standard malien) et exclut volontairement les périodes propres à une classe
(`school_class__isnull=False`, bulletins_views.py:82). Une classe en périodes « personnalisées »
réapparaît donc sous les compositions de son cycle. **Décision user (test day) : on reste cycle-based**
— une classe mal classée se corrige via son NIVEAU (édition classe, bug corrigé Lot A), pas via des
périodes personnalisées. Câbler complètement les périodes par classe dans tout le flux bulletins =
gros chantier pour un cas rare → **reporté**. Si un jour un besoin réel émerge (une classe qui diffère
vraiment de son cycle), rouvrir ; sinon envisager de retirer l'option « personnaliser une classe »
pour éviter la confusion.

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

### Révision élève — niveau 2 : dates de compositions/examens saisies par l'école ⭐ vrai atout
Quand la Révision (SRS) tournera : permettre à l'école de saisir les **dates de compositions/examens**
par classe et par matière → le plan de révision de l'élève **s'intensifie automatiquement** à l'approche
(« composition de Français dans 10 jours → priorité aux concepts fragiles de Français »).
Troisième signal d'ordonnancement après (1) courbe d'oubli et (2) emploi du temps du lendemain
(CourseSlot, déjà en base). Aucune app concurrente ne peut le faire : nous possédons les vraies
données de l'école. **À ne pas oublier — post-lancement, après le SRS de base.**

### Migration modèle IA — Gemini 3 Flash (réduction du coût de génération ~81%)
Aujourd'hui : Claude Sonnet 4.6 ($3/$15 par M tokens), appel codé en dur dans services.py
(4 endroits : Architecte, B1, B2, B3). Coût observé ~$0.30/leçon riche ; une Terminale complète
(≈147 leçons) ≈ 96 500 FCFA une fois.
**Cible recommandée : Gemini 3 Flash ($0.50/$3)** → même Terminale ≈ 18 400 FCFA (−81 %), vision
native (lit les scans de manuels), déjà prévu dans AIProvider.GEMINI. Le tout dernier étage
(Flash-Lite, −97 %) est écarté : risque sur la qualité pédagogique de B1 (concepts+quiz).
**Méthode : ne PAS basculer à l'aveugle.** (1) Implémenter le chemin client Gemini (les prompts
sont réglés pour Claude → re-tester), (2) **test A/B qualité** sur 3-4 vraies leçons (quiz,
explications, français, lecture de scans), (3) si B1 faiblit → hybride (Claude pour B1 seul) ou
monter à Gemini 3.5 Flash. Bonus : **Batch API −50 %** (génération non temps-réel) → ~9 200 FCFA/Terminale.
Le coût IA n'est PAS le risque de survie (~10% du prix parent) → optimisation de marge à l'échelle,
à faire après le développement des chantiers en cours. **Ne pas oublier.**

### Histoire v3 — décision produit posée : CASTING FIXE « Missions » (modèle Duolingo)
Verdict (recherche mondiale) : les personnages inventés par l'IA à chaque leçon = MORTS (qualité
aléatoire, zéro attachement, colle mal aux maths/code). Le modèle prouvé = **casting fixe dessiné
UNE fois** (Duolingo : continuité type série TV, attachement émotionnel, marche pour Duolingo
Math aussi). Plan retenu, à attaquer APRÈS le chantier Usage sain :
1. Créer 2 personnages maliens canoniques (garçon + fille) — brouillons SVG d'abord, puis
   illustrateur/Figma (coût unique, plusieurs expressions). Ils deviennent l'identité de l'app
   (missions, encouragements quiz/cahier, cartes de connexion).
2. L'histoire devient « Mission » : le duo accompagne l'élève dans TOUTE matière (marché=maths,
   labo=physique…). L'IA n'invente plus les personnages, elle écrit leurs dialogues (prompt
   contraint = qualité stable). Player scène (maquette « La Scène » posée : décor plein écran,
   bulles BD, question dans la scène — artifact 9ca5e7de).
3. **Niveau 2 (étoile polaire)** : explorables interactifs générés par l'IA pour maths/physique/
   code (modèle Brilliant — manipuler jusqu'à ce que ça clique) en remplacement/enrichissement
   de la Mission sur les matières scientifiques. Quasi inexistant sur le marché = différenciateur.

### Cahier élève — niveau 2 : bloc IA dédié « B4 Cahier »
Le Cahier v1 est livré en **Voie B** (dérivation du contenu déjà généré, sans IA : dictée depuis
la lecture, copie du glossaire, composition depuis un concept). Niveau 2 = un **bloc de génération
B4 dédié** (comme B1/B2/B3) qui produit de vraies tâches calibrées : dictées choisies au bon niveau,
et surtout **corrigés-types de composition pour le lycée** (aujourd'hui pauvres car dérivés d'un
concept). Nouveau prompt + coût de génération + régénération des leçons → à faire après lancement.

### Auth staff par e-mail (prof / staff / directeur / promoteur) — décision produit posée
Direction retenue : **e-mail pour le personnel** (reset self-service « mot de passe oublié »),
**téléphone pour les parents** (inchangé). Conditions à valider AVANT de construire :
(1) les profs cibles ont-ils un e-mail qu'ils consultent ? (directeurs oui, vacataires à vérifier) ;
(2) infra d'envoi d'e-mails (SendGrid/Mailgun…) à poser au déploiement ;
(3) double régime de connexion → page login + modèle à concevoir.
**Niveau 1 (intérimaire) FAIT** en attendant : mot de passe staff temporaire à usage unique
(**changement forcé** à la 1re connexion, comme les parents) + **régénération** par le directeur
depuis la fiche membre (l'impasse « staff qui oublie son mdp » est donc résolue sans e-mail).
L'e-mail reste le chantier de fond pour le self-service (sans passer par le directeur).

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

5. ~~**Nombre de tranches libre**~~ **FAIT** (branche `feature/chantiers-suivants`) : CRUD gabarits 1–12.
   ⏸️ **Reste parqué (post-lancement, NE PAS anticiper)** : passer du modèle « nombre » à un modèle « rythme »
   (`kind` = Annuel / Par période auto-adaptatif au cycle / Personnalisé). L'analyse est bonne — le moteur cale
   déjà les tranches sur les périodes *du cycle de l'élève* (`periods_for_class`) quand nombre == nb de périodes,
   donc un gabarit à nombre fixe ne peut pas dire « par période » pour une école fondamental+secondaire. **Mais
   c'est une décision produit, pas technique** : à ne construire QUE si une vraie école demande « facturer par
   période sur plusieurs cycles ». Sinon un gabarit par classe suffit.
6. **Cosmétique matières** — collision de couleur auto entre 2 matières ; abréviation affichée trop pâle. *(couleur auto-distincte déjà faite ; reste l'abréviation pâle.)*
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
- **Relances automatiques impayés** (SMS J+5 / J+15). ⚠️ La relance **manuelle est FAITE** : écran Paiements (onglet
  « En retard », liste rouge triée) + boutons « Relancer » / « Tout relancer » → notification **in-app** aux
  responsables (`_send_reminder` → `notify_guardians`, anti-spam 1×/jour). Reste à faire = le volet **automatique**
  (cron/tâche planifiée — inexistant aujourd'hui) et un **canal SMS/email** (la relance est in-app seule).
- **Restes du chantier multi-école** : portail parent multi-école + **transfert d'élève entre écoles** (historique préservé).

### Dette technique / polish
> Audité juillet 2026 : **`brand-blue → primary` FAIT** (focus ring restauré, 4 fichiers) ;
> **alerte émargement** et **`components.css` orphelin** = déjà faits/inexistants (retirés).
- ⚠️ **Examen élève : incohérence génération ↔ affichage.** Le prompt de génération autorise les
  **13 types** de quiz dans les examens (`services.py:640` « mêmes types ») mais `exam_runner_v2.html`
  n'en REND que **5** (mcq_single/multiple, true_false, cloze_test, matching) → une question d'un
  autre type dans un examen = **invisible/cassée** pour l'élève. Remèdes possibles : (a) rendre les
  13 types dans le runner examen, ou (b) restreindre le prompt examen aux 5 rendus (1 ligne).
  Constaté pendant le montage du banc de QA élève (matière « Test »).
- Cosmétiques divers : carte dashboard demi-largeur, erreurs Alpine console, labels de groupe HTMX orphelins (notifications).

*(Déjà faits, donc retirés du backlog : catalogue de frais + échéancier par tranches, liste rouge des impayés,
portail parent financier, périodes par cycle.)*
