# Module Finances — Plan & Évolution

Branche : `feature/finance-module` (depuis `develop`)
Dernière mise à jour : 2026-06-27 — Lot 2 terminé

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
- [x] **Lot 2 — Catalogue de frais** : modèles catalogue + variantes + écran de config école.
- [x] **Lot 3 — Fiche financière par année** : postes élève + échéancier + allocation, liés à l'enrollment actif.
- [ ] **Lot 4 — Inscription enrichie** : flux 3 clics générant la fiche financière à l'inscription. _(4a fait : fondation enrollment + inscription unitaire enrichie. 4b à venir : enrichissement de l'import de masse — colonne genre, options.)_
- [ ] **Lot 5 — Encaissement + timeline** : écran de paiement au guichet (timeline de tranches colorées).
- [ ] **Lot 6 — Tableau de bord impayés** : liste rouge filtrée par date d'échéance.
- [ ] **Lot 7 — Passage de classe** : flux de fin d'année (régénération fiche année N+1) — boucle et valide l'architecture annuelle.

## Décisions actées
- Bus/cantine = **abonnements** mensuels résiliables ou forfait annuel, **pas** des tranches de scolarité.
- Frais à **variantes** (un concept unique couvre tenue, bus, cantine).
- Scolarité reste **par classe** (`SchoolClass.annual_fee`), découpée par gabarit.
- Inscription = frais ponctuel annuel, règle « nouveaux / anciens » configurable au niveau école.
- Passage de classe construit **maintenant** (lot 7) pour valider l'architecture, pas reporté.
- **Frais nouveaux/anciens (lot 3)** : champ `applies_to` sur `FeeType` (NEW / RETURNING / ALL) + `returning_amount` nullable. Configurable ET automatique : le socle du lot 1 sait reconnaître un ancien élève via un `StudentEnrollment` de l'année précédente (présence d'un enrollment antérieur dans la même école). NEW = uniquement nouveaux inscrits, RETURNING = uniquement anciens (avec éventuel `returning_amount` réduit), ALL = tous.
- **Fiche financière = TROIS familles de dettes indépendantes**, jamais fondues : (a) scolarité en tranches datées, (b) frais ponctuels one-shot, (c) abonnements mensuels résiliables. L'allocation d'un paiement se fait **à l'intérieur de chaque famille**, jamais dans un sac FIFO commun — un versement scolarité ne solde pas une dette cantine, et inversement.
- **Dates des tranches** : portées par le gabarit `PaymentScheduleTemplate`, **pré-remplies depuis les `Period` existants** de l'année active (cf. `schools.Period`), puis ajustables à la génération de l'échéancier.

## Évolutions futures (hors périmètre actuel)
- **Montant de frais variable par niveau/classe** (ex. inscription Jardin ≠ inscription 9ème). V1 : montant unique par frais ; une école qui en a besoin crée des frais distincts (ex. « Inscription primaire », « Inscription collège »). À implémenter plus tard via une petite table « montant par niveau » accrochée au `FeeType`, si la demande émerge.
- **Nettoyage `components.css` orphelin** (`brand-blue` hors build) — à supprimer ou réaligner sur `primary`. Hors périmètre finances.
- **Import 1000 élèves synchrone** — à valider en charge ; passer en asynchrone si nécessaire. Dépend de l'infra de tâches de fond (Celery/worker), **non décidée** à ce jour (aujourd'hui : aucune, hors thread daemon ad hoc des leçons).

## Points de vigilance (relevés aux audits)
- Incohérence charte : `brand-blue` (components.css) vs `primary-600/700` (templates) — trancher la couleur officielle.
- Bug latent fiche élève : template référence `payment.is_valid` / `payment.paid_at`, champs absents du modèle (`is_cancelled`, `payment_date`). À corriger en passant (lot 5).
- Import 1000 élèves synchrone + sérialisation DOM — à valider en charge.
- `School.current_school_year` (CharField décoratif) coexiste avec `SchoolYear.is_active` (structurant) — ne pas confondre.
- `StudentEnrollment` sans contrainte d'unicité aujourd'hui — à ajouter au lot 1.
- `components.css` orphelin (`brand-blue` hors build) — à supprimer ou réaligner sur `primary`, hors périmètre finances.

## Journal des sessions
| Date | Lot | Ce qui a été fait |
|------|-----|-------------------|
| 2026-06-27 | — | Création branche + plan initial |
| 2026-06-27 | 3 | Cœur du module. FeeType amendé (`applies_to` NEW/RETURNING/ALL + `returning_amount`, helpers `applies_to_student`/`resolved_amount`). 4 modèles : `StudentFeeAccount` (1/enrollment, agrégats calculés), `FeeDebt` (3 familles via `kind`, snapshot `total_amount`, résiliable), `Installment` (échéance datée, `is_overdue`/`days_overdue`), `PaymentAllocation` (lien Payment↔tranche — immuabilité préservée, aucun solde stocké). Migration `0004`. Services : `build_fee_account` (scolarité+frais obligatoires applicables, variante auto par genre, idempotent), `generate_tuition_installments` (découpe sans perte de franc, dates dérivées des Period sinon segments d'année), `allocate_payment` (FIFO intra-dette, anti sur-allocation, jamais inter-familles). Commande `build_fee_account_for_student`. Bloc fiche élève réparé (`is_valid`→`not is_cancelled`, `paid_at`→`payment_date`) + affichage minimal de la fiche (3 familles, tranches, statuts) avec état neutre si absente. Test e2e 32/32 (NEW vs RETURNING, 100000/3 exact, dates=périodes, allocation partielle/cascade/anti-surallocation/inter-famille, idempotence, vue réparée). Aucun champ Payment ajouté. Base dev intacte (test en rollback). |
| 2026-06-27 | 4a (fix robustesse) | Bug critique : **double encodage JSON** (`json.dumps` dans la vue + `\|json_script` dans le template) → `JSON.parse` rendait une chaîne, `this.fees.filter`/`schedules.find` plantaient, `init()` levait → **tout le composant Alpine mourait** (undefined, options disparues, récap « F » seul). Manifesté pire sur école non configurée mais présent partout (les e2e ne lançaient pas le JS). Corrigé : la vue passe des **objets Python**, `json_script` encode une seule fois. + Robustesse école « démarrage » (0 frais / 0 gabarit) : parsing défensif `safeParse`→[], `currentTemplateCount` repli 1, `currentTemplateName`=« Paiement en une fois », bandeau d'info ambre « pas de catalogue → Paramètres » avec lien, options affichent une raison si vides (jamais un trou), gabarit en état neutre, récap = au moins la scolarité (jamais vide). Validé sous Node sur école vide (#5) ET configurée (#4) : aucune exception, tenue auto 15000, récap correct. |
| 2026-06-27 | 4a | **Fondation enrollment + inscription unitaire enrichie.** Helper `apps/students/services.ensure_active_enrollment` (get_or_create de l'enrollment ACTIVE de l'année active, idempotent, None si pas d'année) branché dans les **3 flux** (unitaire/groupe/import) → plus aucun élève sans enrollment. `build_fee_account` étendu : `fee_selections` (options cochées) + `template` (gabarit choisi) ; abonnements cochés → dette subscription `is_active=True` **sans mensualité d'avance** (1ère au paiement, lot 5). Groupe/import = mode minimal (scolarité + obligatoires, genre nullable). `student_create` : garde-fou « pas d'année active » (422 + toast, pas de 500), lit genre/options/gabarit, crée enrollment + fiche ; `gender` ajouté requis au `StudentCreateForm`. Panneau enrichi (`student_list.html`) : genre segmenté Fille/Garçon obligatoire, bloc « Options et services » (toggles par frais optionnel, tenue auto par genre, select trajet bus), ligne gabarit repliable, **récap live** « à la rentrée » (1ère tranche + ponctuels, abonnements listés à part), bouton désactivé tant que genre/trajet manquants. Contexte JSON (`fees_json`/`schedule_json`) exposé au template. Test e2e 26/26 (Fille+tenue+bus+3 tranches, sans option, sans année active=422, idempotence, groupe). Base dev intacte (rollback). 4b (import enrichi) à venir. |
| 2026-06-27 | 3 (cadrage) | Décisions lot 3 actées : frais nouveaux/anciens (`applies_to` NEW/RETURNING/ALL + `returning_amount`, reconnaissance auto des anciens via `StudentEnrollment` N-1) ; fiche financière = 3 familles de dettes indépendantes (scolarité tranchée / ponctuels / abonnements), allocation intra-famille, jamais FIFO commun ; dates des tranches portées par le gabarit, pré-remplies depuis les `Period`. Section « Évolutions futures » ajoutée (montant par niveau, nettoyage components.css, import async). Audit lecture seule des écrans accueillant les lots 3/5/6. Aucun code modifié hors ce plan. |
| 2026-06-27 | 2 (corrections) | Corrections post-test visuel : (1) icône de carte décorative (`aria-hidden`, non cliquable) + différenciée par frais via `FeeType.get_icon()` (Lucide). (2) Variantes éditables inline (label+montant, auto-save HTMX) — fin du blocage « doublon Garçon » ; `gender_key` préservé. (3) Désactivation via le modal de confirmation maison (`$store.confirm`), suppression du `confirm()` natif. (4) « Supprimer » → **toggle Actif/Inactif** (frais ET variantes), section repliée « Frais désactivés » + réactivation ; contraintes d'unicité rendues **conditionnelles** (`is_active=True`) sur `(school,name)` et `(fee_type,label)` → un nom/libellé désactivé se libère, réactivation sans erreur (migration `0003`). (5) Scolarité sortie des cartes → **bannière d'info** (lien « Gérer les classes ») ; `FeeType` TUITION conservé en base (cohérence échéancier lot 3) mais exclu du catalogue ; non créable via le formulaire. `output.css` rebuildé (badges/utilitaires). Test e2e 18/18, base dev nettoyée. |
| 2026-06-27 | 2 | Nouvelle app `apps.finance`. Modèles `FeeType` (catalogue : catégorie one_time/tuition/subscription, montant nullable, obligatoire/variantes/genré), `FeeVariant` (label+montant+gender_key, unique par frais), `PaymentScheduleTemplate` (gabarit tranches, un seul défaut/école). Migrations `0001`+`0002`. Écran settings « Frais & tranches » (`/settings/frais/`) : catalogue en cartes (montant inline, badge « Par classe » scolarité, variantes), gabarits sélectionnables, état vide accueillant, HTMX+Alpine+toasts, classes UI réutilisées, primary-* only, responsive. Seed manuel (bouton dev + commande `seed_fee_catalog`). Test e2e 14/14 (CRUD frais/variantes, défaut unique, doublons refusés). Aucun champ Payment touché. |
| 2026-06-27 | 1 | Champ `Student.gender` (M/F, nullable) + `Gender` TextChoices. Contrainte unique conditionnelle `uniq_enrollment_student_year` sur `StudentEnrollment (student, school_year)` (condition `school_year__isnull=False`). Docstring « source de vérité » sur le modèle. Migration schéma `0006` + data migration `0007` (backfill enrollments ACTIVE des élèves actifs vers l'année active, idempotente, reverse no-op). Backfill vérifié : 1074/1074 élèves rattachés, 0 doublon, école sans année active ignorée. Aucune UI touchée. |
