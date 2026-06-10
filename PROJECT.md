# EduApp — Référence projet

---

## Vue générale

**Nom** : EduApp
**Description** : SaaS de gestion scolaire pour établissements privés en Afrique francophone.
Couvre la gestion des classes, l'inscription des élèves, les paiements, les bulletins et la communication avec les parents.
**Cible marché** : Écoles primaires, collèges et lycées privés — Côte d'Ivoire en premier, puis expansion UEMOA.
**Langue** : Français (i18n activé, base pour ajout arabe/anglais)
**Seed démo** : `python manage.py seed_demo` → école id=1, 6 classes CP1→CM2, superuser `tel=0000000000` / `pwd=admin123`

### Stack technique

| Couche | Technologie |
|---|---|
| Backend | Django 6.0.6 |
| Base de données | PostgreSQL (`db=eduapp_db`, `user=sy`) |
| Interactions UI | HTMX 2.0.4 (CDN) |
| Réactivité UI | Alpine.js 3.x (CDN) |
| CSS | Tailwind CSS CDN (→ build local en production) |
| Auth | Modèle `User` custom, login par numéro de téléphone |
| Fichiers statiques | Whitenoise |
| Config | python-decouple (.env) |
| Excel | openpyxl 3.1.5 |
| Images | Pillow 12.2.0 |
| HTMX middleware | django-htmx 1.27.0 |

### Architecture dossiers

```
EduApp/
├── apps/
│   ├── accounts/       → User custom, rôles, auth, superadmin
│   ├── core/           → get_school(), SchoolMixin, SchoolMiddleware
│   ├── schools/        → School, SchoolClass, SchoolYear, Period,
│   │                     Subject, ClassSubject, Note + settings_views
│   ├── students/       → Student
│   └── payments/       → Payment
├── config/
│   ├── settings.py
│   └── urls.py
├── templates/
│   ├── base.html       → sidebar desktop + nav-bottom mobile
│   ├── includes/       → composants réutilisables (search_bar.html)
│   ├── schools/
│   │   ├── class_list.html
│   │   └── partials/   → class_row, class_table_body, class_stats, class_import_preview…
│   ├── settings/       → school_years, school_year_periods, subjects
│   │   └── partials/   → school_year_form/list, period_card/form/list,
│   │                     subject_form/list, class_subjects, toast, nav_item…
│   └── superadmin/     → dashboard, school_create, director_create
├── PROJECT.md
└── requirements.txt
```

---

## Design system

### Couleurs principales

| Nom | Hex | Usage |
|---|---|---|
| `brand-blue` | `#1E3A5F` | Sidebar, boutons primaires, titres |
| `brand-gold` | `#F5A623` | Bouton CTA principal, accents |
| `brand-light` | `#F0F4F8` | Fond de page (`bg-brand-light`) |

### Badges niveaux scolaires

| Niveau | `level` (DB) | Fond | Texte |
|---|---|---|---|
| Primaire | `primary` | `#EAF3DE` | `#27500A` (vert) |
| Collège | `middle` | `#E6F1FB` | `#0C447C` (bleu) |
| Lycée | `high` | `#FAEEDA` | `#633806` (orange) |
| Université | `university` | `#F3F4F6` | `#374151` (gris) |

### Badges statut classe

- **Complet** → `bg-red-100 text-red-700`
- **Disponible** → `bg-green-100 text-green-700`

### Règles composants

- **Bouton primaire** : `bg-brand-gold hover:bg-yellow-500 text-white font-semibold px-5 py-2.5 rounded-lg min-h-[44px]`
- **Bouton secondaire** : `bg-white border border-brand-blue text-brand-blue font-semibold px-4 py-2.5 rounded-lg`
- **Bouton destructif** : hover `text-red-600 bg-red-50`
- **Cards** : `bg-white rounded-xl shadow-sm border border-gray-100 p-5`
- **Modals** : Alpine `x-show` + `x-transition`, overlay `bg-black/40 z-50`, contenu `rounded-2xl shadow-2xl max-w-lg`
- **Sidebar** : `w-64 bg-brand-blue` fixe desktop, cachée mobile
- **Nav mobile** : bottom bar 4 items fixe `bg-brand-blue`, icônes + labels
- **HTMX indicator** : `.htmx-indicator` opacity 0→1, spinner SVG `animate-spin`
- **Taille tactile min** : `min-h-[44px]` sur tous les boutons interactifs
- **Masquage Alpine** : `[x-cloak] { display: none !important; }` dans base.html
- **Toggle vue** : `hidden lg:flex` — switch cards/tableau masqué sur mobile
- **CSRF HTMX** : `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` sur `<body>`

---

## Modèle économique

### Forfaits école (en FCFA/mois — à confirmer)

| Forfait | Capacité | Prix |
|---|---|---|
| Starter | jusqu'à 150 élèves | À définir |
| Standard | jusqu'à 500 élèves | À définir |
| Premium | illimité | À définir |

### Module parent (optionnel)

- Accès portail parent + notifications SMS/WhatsApp
- Paiement Mobile Money via **Orange Money** (intégration API à prévoir)
- Facturation à l'école, pas au parent

---

## Rôles et permissions

| Rôle (`role`) | Description | Peut faire |
|---|---|---|
| `director` | Directeur de l'école | Tout (gestion classes, élèves, paiements, staff, rapports) |
| `staff` | Secrétaire / administratif | Inscription élèves, encaissement paiements, reçus |
| `teacher` | Professeur | Consulter sa classe, saisir notes/absences |
| `student` | Élève | Portail personnel : notes, bulletins, solde |
| `parent` | Parent d'élève | Consulter bulletin, solde, payer en ligne |

**Superuser** (`is_superuser=True`) : accès `/superadmin/` — gestion multi-école, création comptes directeurs.

---

## Modèles de données

### `School` (`apps/schools`)
| Champ | Type |
|---|---|
| `name` | CharField(200) |
| `city` | CharField(100) |
| `country` | CharField(100, default="Côte d'Ivoire") |
| `phone_number` | CharField(20, blank) |
| `email` | EmailField(blank) |
| `logo` | ImageField(upload_to='schools/logos/', blank) |
| `is_active` | BooleanField(default=True) |
| `created_at` | DateTimeField(auto_now_add) |

### `SchoolClass` (`apps/schools`)
| Champ | Type |
|---|---|
| `school` | FK → School |
| `name` | CharField(100) |
| `level` | CharField choices `EducationLevel` : primary/middle/high/university |
| `annual_fee` | DecimalField(FCFA, validators≥0) |
| `max_capacity` | PositiveSmallIntegerField(null, blank) |
| `notes_delegates` | M2M → User (enseignants autorisés à saisir les notes) |
| `is_active` | BooleanField(default=True) |
| `created_at` / `updated_at` | DateTimeField |

Méthodes : `get_student_count()` (utilise annotation `student_count` si disponible → évite N+1), `is_full()`
Contrainte : `unique_together = [('school', 'name')]`

### `SchoolYear` (`apps/schools`)
| Champ | Type |
|---|---|
| `school` | FK → School |
| `name` | CharField(20) — ex : `2025-2026` |
| `start_date` / `end_date` | DateField |
| `is_active` | BooleanField |

`clean()` : une seule année active par école. `unique_together = [('school', 'name')]`

### `Period` (`apps/schools`)
| Champ | Type |
|---|---|
| `school_year` | FK → SchoolYear |
| `name` | CharField(100) — ex : `Trimestre 1` |
| `period_type` | TextChoices : `trimester` / `semester` / `custom` |
| `start_date` / `end_date` | DateField |
| `order` | PositiveSmallIntegerField |
| `is_notes_open` | BooleanField — toggle saisie notes |

### `Subject` (`apps/schools`)
| Champ | Type |
|---|---|
| `school` | FK → School |
| `name` | CharField(100) |
| `short_name` | CharField(10) |
| `color` | CharField(7, default `#1E3A5F`) |
| `is_active` | BooleanField — soft delete |

`unique_together = [('school', 'name')]`

### `ClassSubject` (`apps/schools`)
Table de liaison SchoolClass ↔ Subject avec paramètres pédagogiques.
| Champ | Type |
|---|---|
| `school_class` | FK → SchoolClass |
| `subject` | FK → Subject |
| `coefficient` | DecimalField(3,1) |
| `note_system` | TextChoices : `moyenne_simple` / `devoirs_compo` |
| `coeff_devoirs` / `coeff_compo` | DecimalField(3,2) — doivent sommer à 1 |
| `max_grade` | DecimalField(5,2, default 20) |
| `teacher` | FK → User (null) |
| `order` | PositiveSmallIntegerField |
| `is_active` | BooleanField |

`clean()` : `coeff_devoirs + coeff_compo == 1` en mode `devoirs_compo`.

### `Note` (`apps/schools`)
| Champ | Type |
|---|---|
| `class_subject` | FK → ClassSubject |
| `student` | FK → Student (related_name=`grade_notes`) |
| `period` | FK → Period |
| `note_type` | TextChoices : `devoir` / `composition` / `examen` |
| `value` | DecimalField(5,2) |
| `entered_by` | FK → User |
| `entered_at` | DateTimeField(auto_now_add) |

`clean()` : `value ≤ class_subject.max_grade`. Index DB : `(student, period, class_subject)`.

### `Student` (`apps/students`)
| Champ | Type |
|---|---|
| `school` | FK → School (related_name='students') |
| `school_class` | FK → SchoolClass (related_name='students') |
| `full_name` | CharField(200) |
| `date_of_birth` | DateField(null, blank) |
| `phone_number` | CharField(20, blank) |
| `parent_phone_number` | CharField(20, blank) |
| `access_code` | CharField(8, unique, auto-généré UUID hex) |
| `tuition_fee` | DecimalField (copié de la classe à l'inscription) |
| `notes` | TextField(blank) |
| `is_active` | BooleanField(default=True) |
| `enrolled_at` / `updated_at` | DateTimeField |

Méthodes : `get_total_paid()`, `get_balance_due()`, `get_payment_status()` → `'paid'`/`'partial'`/`'unpaid'`

### `User` (`apps/accounts`)
| Champ | Type |
|---|---|
| `phone_number` | CharField(20, unique) — USERNAME_FIELD |
| `email` | EmailField(blank) — obligatoire pour directeurs |
| `full_name` | CharField(150) |
| `role` | CharField choices `UserRole` : director/staff/teacher/student/parent |
| `school` | FK → School (null, blank) |
| `is_active` | BooleanField |
| `is_staff` | BooleanField |
| `created_at` | DateTimeField |

### `Payment` (`apps/payments`)
| Champ | Type |
|---|---|
| `student` | FK → Student |
| `amount` | DecimalField(FCFA, validators≥1) |
| `payment_method` | CharField choices : cash/mobile_money/bank_transfer/check |
| `paid_at` | DateTimeField(auto_now_add) |
| `receipt_number` | CharField(50, unique, auto `REC-{uuid[:10]}`) |
| `collected_by` | FK → User |
| `notes` | TextField(blank) |
| `is_valid` | BooleanField(default=True) — soft cancel |

---

## Ce qui est terminé

### Fondation bulletins — Étape 1/3 (`/settings/school-years/`, `/settings/subjects/`)
- **6 nouveaux modèles** : `SchoolYear`, `Period`, `Subject`, `ClassSubject`, `Note` + `notes_delegates` sur `SchoolClass`
- **Migration** `0003_grades_foundation` — appliquée
- **Années scolaires** : créer, activer/archiver (validation 1 seule active), gérer les périodes
- **Génération périodes** : bouton « 3 Trimestres » ou « 2 Semestres » auto-découpe l'année
- **Saisie périodes manuelle** : formulaire collapse HTMX
- **Toggle saisie notes** : ouvre/ferme la saisie par période (OOB swap sur la card)
- **Matières** : créer (avec suggestions rapides pré-remplissables), soft delete
- **Matières par classe** : panel HTMX (select → load), ajouter/modifier inline/retirer
- **OOB swaps** : liste rafraîchie côté serveur après chaque action, pas de rechargement page
- `HX-Trigger schoolYearSaved / subjectSaved` → Alpine ferme le panneau auto
- **2 nouvelles sections** sidebar activées : Années scolaires + Matières

### Module Notes (`/notes/`)
- **Dashboard** progression par classe/matière : cartes avec barres de remplissage
- **Saisie notes HTMX** sauvegarde immédiate au focusout/Enter (upsert)
- **Recalcul moyenne temps réel** Alpine.js via `HX-Trigger`
- **Flash vert/rouge** feedback visuel après sauvegarde (1,2s / 2,5s)
- **Navigation clavier** Tab/Entrée pour passer à la cellule suivante
- **Onglets matières Alpine.js** avec état actif (fond bleu `#1E3A5F`)
- **Cellules éditables** hauteur `h-[36px]` corrigée pour zone cliquable
- **Colonne nom sticky** gauche pour défilement horizontal mobile
- **`can_enter_notes()`** contrôle d'accès par rôle (directeur/staff toujours, prof si assigné + période ouverte)
- Support **devoirs+composition** (2 colonnes pondérées) et **moyenne simple** (colonnes dynamiques)
- Bouton "Ajouter une évaluation" en mode moyenne simple
- Annulation soft des notes (directeur/staff)
- Stats classe temps réel (moy. classe, meilleur, faible)
- **Recherche instantanée** Alpine.js dans le tableau de saisie (filtrage local, zéro requête serveur)

### Module Bulletins (`/bulletins/`)
- **4 nouveaux modèles** : `AppreciationScale`, `BulletinConfig` (1:1 école), `Bulletin`, `BulletinLine`
- **Migration** `0005_bulletins` — appliquée
- **Calcul automatique** des moyennes matière et générales avec `BulletinCalculator`
- Support **devoirs+composition** (pondération 40/60) et **moyenne simple**
- **Cas limites gérés** : matière sans note exclue du total des coefficients
- **Génération PDF WeasyPrint** au format officiel malien
  - En-tête ministériel configurable (texte gauche/droite, logo)
  - "RELEVÉ DE NOTES DU...", tableau colonnes N.Classe/Comp×2/Moy(1+2)
  - Format **pleine page A4** ou **2 par page A4** avec ligne pointillée de découpe
  - Signatures bas de page (Le Parent / Le Directeur)
- **3 onglets interactifs** :
  - 📊 **Santé éducative** : 4 stats (moy. classe, taux réussite, admis, difficulté), Top 3 podium, alertes élèves <10, bouton génération
  - 📋 **Bulletins** : liste des élèves avec statut (généré/prêt/notes manquantes), génération individuelle ou en masse, preview modal, téléchargement PDF/ZIP
  - 🏆 **Classements** : tableau trié par moyenne, médailles podium, statistiques récapitulatives (moy. classe, premier, dernier, effectif)
- **Barème appréciations** personnalisable via `AppreciationScale.get_appreciation()`
- **Génération optimisée** : 1 requête notes, `bulk_create` Bulletin + BulletinLines, calcul rangs en 1 passe
- **Recherche instantanée** Alpine.js avec `$store.search` (onglets Bulletins et Classements)
- **Sécurité** : isolation école, generation director/staff uniquement, aperçu et download contrôlés
- **Multi-format** : téléchargement PDF individuel ou ZIP classe complète
- **URL** : `/bulletins/` — lien activé dans la sidebar

### Dashboard V1 (`/dashboard/`)
- **6 KPI cards** avec counters animés (0 → valeur réelle en 1.2s ease-out cubique, `requestAnimationFrame`)
- **Alertes intelligentes** 3 niveaux (🔴 critique : impayés > 30j / 🟡 attention : moyenne < 8/20 / 🟢 info : bulletins prêts) — dismissibles avec transition
- **Graphiques Chart.js** données réelles :
  - Courbe inscriptions cumulées par mois (filtre `enrolled_at__date__lte`)
  - Barres revenus mensuels (filtre `payment_date__year` + `__month`) + ligne objectif pointillée
  - États vides avec lien vers l'action correspondante
- **Tableau santé éducative par classe** : moy. générale, taux réussite, paiements, statut 🟢🟡🔴, filtre niveau (primaire/collège/lycée), ligne cliquable → bulletins
- **Timeline 10 dernières actions** : paiements, bulletins, notes, inscriptions — slide-in gauche, icônes par type
- **FAB mobile** : bouton + flottant bas droite, rotation au clic, 4 actions en fan (Inscrire/Paiement/Notes/Bulletins)
- **États vides élégants** : message + lien d'action pour chaque section sans données
- **Filtres mensuels graphiques corrigés** : génération de la liste des mois entre start_date et end_date
- **Actions rapides desktop** : barre horizontale avec 4 boutons d'accès direct
- **Redirection login** : director/staff → `/dashboard/` (au lieu de `/classes/`)
- **URL** : `/dashboard/` — lien **Dashboard** en premier dans la sidebar

### Interface Classes (`/classes/`)
- Liste avec vue **cards** (défaut) et **tableau** triable — switch persisté localStorage
- Switch vue `hidden lg:flex` — masqué sur mobile
- **3 stats** en temps réel via HTMX OOB swap : classes actives, élèves inscrits, taux de remplissage
- **Recherche** live HTMX 300ms debounce, composant réutilisable `includes/search_bar.html`
- **Créer classe** : modal Alpine.js + HTMX POST → met à jour liste + stats
- **Éditer classe** : inline row edit HTMX
- **Supprimer classe** : soft delete (bloqué si élèves inscrits)
- **Import Excel/CSV** : modal 2 étapes, template `.xlsx` téléchargeable, aperçu + détection doublons, rapport d'erreurs ligne par ligne, confirmation en masse

### Superadmin (`/superadmin/`)
- Accessible uniquement `is_superuser=True` (décorateur `@superadmin_required`)
- **Dashboard** : 3 stats globales + liste toutes les écoles (classes, élèves, directeur)
- **Créer école** → flow 2 étapes → **Créer directeur** (email obligatoire, double mot de passe)
- Alerte si école sans directeur, lien rapide de création
- Templates autonomes (`base_superadmin.html` sans sidebar app)
- Lien Superadmin dans sidebar (badge doré, visible si `is_superuser`)

### Qualité / Sécurité
- **N+1 éliminés** : `_classes_qs()` avec `annotate(student_count=Count(...))`, `get_student_count()` utilise l'annotation
- **Superadmin dashboard** : `annotate(classes_count, students_count)` + `prefetch_related(directors)`
- **Isolation multi-tenant** : tous les `get_object_or_404` filtrent `school=get_school(request)`
- **Auth** : `@login_required` sur toutes les vues, `@superadmin_required` sur superadmin

### Authentification custom (`/login/`)
- **Login par numéro de téléphone** — `PhoneBackend` + `LoginForm` avec messages d'erreur précis
- **Rate limiting** : 5 échecs consécutifs → blocage 15 minutes (cache Django)
- **Logout** avec toast de confirmation de déconnexion
- **Redirection intelligente par rôle** : superuser → `/superadmin/`, director/staff → `/classes/`
- **Session** : expire après 8h d'inactivité (`SESSION_COOKIE_AGE` + `SESSION_SAVE_EVERY_REQUEST`)
- **Vrai multi-tenant** : `get_school(request)` unique source de vérité, `SchoolMiddleware` → `request.school` dans les templates
- `get_demo_school()` supprimé intégralement (27 occurrences dans 4 fichiers)

---

## Prochaines étapes dans l'ordre

1. ~~**Inscription élèves**~~ ✅ terminé
2. ~~**Paiements + reçus PDF**~~ ✅ terminé
3. ~~**Login custom + vrai multi-tenant**~~ ✅ terminé
4. **Bulletins PDF** — en cours
   - ~~**Étape 1** : Modèles fondation (SchoolYear, Period, Subject, ClassSubject, Note) + settings UI~~ ✅
   - **Étape 2** : Saisie des notes (vue professeur/staff, formulaires notes par période)
   - **Étape 3** : Génération bulletin PDF (WeasyPrint, layout A4, header école)
5. **Portail professeur** — liste classes, absences
6. **Portail élève** — style Duolingo, notes, bulletins, solde
7. **Portail parent** — bulletin, solde, paiement Orange Money

---

## Dette technique à corriger

- [✅] **`DEMO_SCHOOL_ID` remplacé par `get_school(request)`** — `get_demo_school()` supprimé dans les 4 fichiers de vues

- [✅] **`LOGIN_URL` corrigé vers `accounts:login`** — PhoneBackend + LoginForm + vues en place

- [✅] **Multi-tenant réel en place** via `get_school(request)`, `SchoolMixin`, `SchoolMiddleware`

- [ ] **Tailwind CDN → build local** pour la production (performance + purge CSS)

---

## Règles de code non négociables

1. **Pas de N+1** : toujours `select_related` / `prefetch_related` / `annotate` sur les querysets de liste
2. **Isolation école** : tout `get_object_or_404` sur un objet appartenant à une école doit filtrer `school=`
3. **Auth** : toute nouvelle vue doit avoir `@login_required` (ou `@superadmin_required`)
4. **HTMX partials** : les réponses HTMX renvoient des partials, jamais la page entière
5. **OOB swaps** : quand une action modifie N zones de la page, utiliser `hx-swap-oob` (ex: stats + liste)
6. **Pas de JS inline** : logique UI dans Alpine `x-data`, logique serveur dans les vues Django
7. **Formulaires Django** : toujours utiliser des `ModelForm`, jamais construire des requêtes manuellement
8. **Soft delete** : ne jamais supprimer physiquement (`is_active=False`), sauf si aucun élève lié
9. **Monnaie** : stocker en FCFA entier (`DecimalField decimal_places=0`), afficher avec `|intcomma`
10. **Templates** : un partial = un seul concept, nommage `partial_<objet>_<action>.html`
11. **Commits** : feat / fix / docs / refactor — message en français, détail des fichiers touchés

---

## Vision Dashboard (construction progressive)

### Dashboard V1 — Données admin (maintenant)
Widgets disponibles :
- Résumé financier : encaissé/dû/solde
- Élèves par statut paiement (graphique donut)
- Évolution inscriptions (graphique courbe)
- Alertes impayés critiques
- Classes les plus chargées
- Activité récente (timeline)

### Dashboard V2 — Après portail prof
Widgets à ajouter :
- Taux d'absences par classe
- Alertes absences non justifiées
- Notes publiées récemment
- Alertes comportement élèves
- Taux de complétion des leçons

### Dashboard V3 — Final surpuissant
Widgets à ajouter :
- Taux de réussite par classe/matière
- Progression élèves sur le trimestre
- Comparaison trimestres (évolution)
- Position des classes entre elles
- Drill-down : clic sur stat → détail complet
- Alertes intelligentes (élève en difficulté)
- Prévisions paiements fin d'année
- Heatmap activité élèves
- Graphique revenus vs objectif annuel

### Principes dashboard
- Animation = vivant (transitions, counters)
- Interactivité = on peut agir dessus
- Intelligence = aide à prendre une décision
- Drill-down sur chaque métrique
- Filtres : par classe, par période, par statut
- Responsive : même richesse sur mobile
- Inspirations : Stripe, Linear, Vercel Analytics
