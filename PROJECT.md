# EduApp — Référence projet

---

## Vue générale

**Nom** : EduApp
**Description** : SaaS de gestion scolaire pour établissements privés en Afrique francophone.
Couvre la gestion des classes, l'inscription des élèves, les paiements, les bulletins et la communication avec les parents.
**Cible marché** : Écoles primaires, collèges et lycées privés — Mali en premier, puis expansion UEMOA.
**Langue** : Français (i18n activé, base pour ajout arabe/anglais)
**Seed démo** : `python manage.py seed_demo` → école id=1, 6 classes CP1→CM2, superuser `tel=0000000000` / `pwd=admin123`

### Stack technique

| Couche | Technologie |
|---|---|
| Backend | Django 6.0.6 |
| Base de données | PostgreSQL (`db=eduapp_db`, `user=sy`) |
| Interactions UI | HTMX 2.0.4 (CDN) |
| Réactivité UI | Alpine.js 3.x (CDN) |
| CSS | Tailwind CSS CLI (build local, `npm run build:css`, `static/css/output.css`) |
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

### Badges niveaux scolaires (niveaux maliens officiels)

| Niveau | `level` (DB) | Classes Tailwind |
|---|---|---|
| Préscolaire | `prescolaire` | `bg-purple-100 text-purple-700 border-purple-200` |
| Fondamental 1er Cycle | `fondamental_1` | `bg-blue-100 text-blue-700 border-blue-200` |
| Fondamental 2ème Cycle | `fondamental_2` | `bg-indigo-100 text-indigo-700 border-indigo-200` |
| Secondaire Général | `secondaire_gen` | `bg-green-100 text-green-700 border-green-200` |
| Secondaire Pro | `secondaire_pro` | `bg-teal-100 text-teal-700 border-teal-200` |
| Supérieur | `superieur` | `bg-orange-100 text-orange-700 border-orange-200` |

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
- **Sidebar collapsible** : toggle ⊟/⊞ → `w-16` (icônes seules) / `w-64` (icônes + labels) ; préférence persistée `localStorage('sidebarOpen')` ; offset footer et contenu principal calculé via `$store.sidebar.open` (`:class` Alpine)
- **Recherche globale** : `⌘K` / `Ctrl+K` ouvre modal `$store.search.open`, résultats HTMX live
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
| `country` | CharField(100, default='Mali') |
| `phone_number` | CharField(20, blank) |
| `email` | EmailField(blank) |
| `logo` | ImageField(upload_to='schools/logos/', blank) |
| `receipt_mode` | CharField : `standard` / `custom` |
| `receipt_signer_title` | CharField(100, default='Le Caissier / Directeur') |
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
| `payment_date` | DateField(default=today) |
| `payment_method` | CharField choices : cash/orange_money/wave/other |
| `payment_type` | CharField — type de versement (scolarité, inscription, autre) — prévu |
| `receipt_number` | CharField(50, unique, auto `REC-YYYY-XXXX` séquentiel) |
| `collected_by` | FK → User |
| `notes` | TextField(blank) |
| `is_cancelled` | BooleanField(default=False) — soft cancel |
| `cancelled_at` | DateTimeField(null, blank) |
| `cancellation_reason` | TextField(blank) |
| `created_at` | DateTimeField(default=timezone.now) |

---

## Ce qui est terminé

### Module Équipe (`/team/`)
- **Modèle `StaffPermission`** avec 13 permissions booléennes granulaires
- **5 profils prédéfinis** : Censeur, Comptable, Surveillant, Informaticien, Secrétaire
- **`job_title`** ajouté sur `User` (titre du poste affiché dans les cards et la fiche)
- **Création membres** : enseignant ou staff, mot de passe temporaire généré (`secrets`)
- **Modal mot de passe unique** : affiché une seule fois via `HX-Trigger team-member-added`, clipboard copy
- **Page détail** (`/team/<id>/`) avec en-tête avatar + badges + infos
- **Permissions staff inline** : toggles auto-save HTMX au changement (`requestSubmit`), groupées par catégorie
- **Assignation matières/classes enseignants** : checkboxes par classe, enregistrement partiel HTMX, indicateur "Enregistré" 3s
- **Panel édition slide-in** : HTMX lazy-load, `team-member-updated` → rechargement page détail
- **Désactivation** avec `$store.confirm` modal, card grisée in-place, auto-désactivation bloquée
- **Recherche Alpine.js temps réel** par nom (une barre par section, `data-name` + `x-show`)
- **Cards responsive** : `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`
- **Migration** `0002_add_job_title_staff_permissions` — appliquée

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

### Module Bulletins V2 (`/bulletins/`)
- **4 nouveaux modèles** : `AppreciationScale`, `BulletinConfig` (1:1 école), `Bulletin`, `BulletinLine`
- **Migrations** `0005_bulletins`, `0008_education_level_mali`, `0009_bulletinconfig_structured_header` — appliquées
- **Niveaux scolaires maliens officiels** : `prescolaire`, `fondamental_1`, `fondamental_2`, `secondaire_gen`, `secondaire_pro`, `superieur` — badges colorés par niveau dans l'interface
- **Formule malienne officielle** : `(moy_devoirs + compo × 2) / 3` — double-rounding fix, `calculate_subject_average` retourne Decimal non arrondi
- **Calcul automatique** des moyennes matière et générales avec `BulletinCalculator`
- Support **devoirs+composition** et **moyenne simple** (mode mixte possible)
- **Cas limites gérés** : matière sans note exclue du total des coefficients
- **Génération PDF WeasyPrint** au format officiel malien :
  - En-tête 3 colonnes : Ministère (gauche) · École+titre (centre) · République du Mali (droite)
  - Colonnes tableau : Notes Classe | Comp×2 | Moy.(1+2×2)/3 | N.×Coef | Appréciations
  - Stats récapitulatives : Moy. générale, Appréciation, Classement, Moy. 1er
  - N.B., date/lieu, signatures (Parent / Directeur / cachet)
- **BulletinConfig structuré** : `ministry_line1/2/3`, `republic_line1/2`, `bulletin_title`, options show_rank/show_logo/etc.
- **Paramètres bulletin** `/settings/bulletin/` : formulaire HTMX complet, toast on save
- **Interface principale améliorée** :
  - Sélecteurs en cartes avec icônes Lucide (calendar / clock / school)
  - Info-bar classe : badge niveau malien coloré + effectif + matières + boutons Générer/ZIP
  - `LEVEL_BADGE` dict avec classes Tailwind par niveau
  - Onglets avec compteur `(22/34)` vert si complet, gris sinon
- **Onglet Bulletins** : barre progression animée, badges statuts avec icônes (check-circle / clock / alert-circle), 3 boutons actions (voir PDF inline / télécharger / imprimer), HTMX indicator
- **Onglet Santé éducative** : 4 stats cards avec cercles d'icônes, podium Top 3 or/argent/bronze, élèves en difficulté avec barre score + lien profil, barres matières triées par moyenne avec indicateur couleur
- **Onglet Classements** : 4 stats cards (moy. classe / moy. 1er / moy. dernier / effectif), podium Top 3 différencié, tableau avec médaille trophy rang 1, export Excel openpyxl, impression `window.print()`
- **Vue PDF inline** : `bulletin_view_pdf` avec `Content-Disposition: inline`, ouverture onglet navigateur
- **Export Excel** : `rankings_export` — colonnes Rang/Nom/Moyenne/Appréciation, en-tête bleu brand, fond doré rang 1
- **Fix N+1** : `select_related('student')` dans `_get_class_stats` et `rankings_tab`
- **Barème appréciations** personnalisable via `AppreciationScale.get_appreciation()`
- **Génération optimisée** : `bulk_create` Bulletin + BulletinLines, calcul rangs en 1 passe
- **Recherche instantanée** Alpine.js `$store.search` (onglets Bulletins et Classements)
- **Sécurité** : isolation école, génération director/staff uniquement, download contrôlé
- **Multi-format** : PDF individuel, ZIP classe complète, Excel classement
- **URL** : `/bulletins/` — sidebar active

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

### Redesign complet (`feature/redesign` → mergé sur `main`)
- **Tailwind CLI** migration CDN → build local (`tailwind.config.js`, `input.css`, `npm run build:css`)
- **Lucide Icons** — zéro emojis, zéro SVG inline dans les templates (bundle CDN + `lucide.createIcons()`)
- **Sidebar blanc** style Notion/Linear (`bg-white`, liens actifs `bg-brand-light`, icônes Lucide)
- **Header sticky** `h-16 bg-white border-b`, titre page dynamique, menu utilisateur dropdown Alpine
- **Menu utilisateur dropdown** : sous-menus "Langue" et "En savoir plus" en `fixed`, fermeture mutuelle
- **Tabs modernes** style Notion (`bg-gray-100 rounded-lg p-1`, actif `bg-white shadow-sm`)
- **Cards standardisées** `border-gray-200 rounded-xl` (suppression shadows lourdes, hover subtil)
- **Typographie Manrope** Google Fonts — chiffres alignés, antialiased, h1/h2/h3 stylés
- **Animations globales** : `fade-in`, `fade-in-up`, `slide-in-right`, `slide-in-up`, skeleton loading, `prefers-reduced-motion`
- **Modals premium** : backdrop-blur-sm, animations scale+translate, bouton X Lucide, footer bg-gray-50
- **Panels slide-in** : `animate-slide-in-right`, overlay `backdrop-blur-[2px]`, border-l subtil
- **États vides premium** : 15 états modernisés (icône Lucide, titre, description, bouton action contextuel)
- **Composants CSS réutilisables** (`@layer components`) :
  - `btn-primary`, `btn-secondary`, `btn-danger`, `btn-ghost`
  - `input-field` (focus ring bleu, placeholder gris)
  - `badge-success`, `badge-warning`, `badge-danger`, `badge-primary`, `badge-purple`, `badge-emerald`
- **Adaptation mobile 23 problèmes** : grilles responsives, tableau paiements scrollable, colonnes cachées mobile, bouton importer visible, switch vue `hidden sm:flex`, inputs tactiles `min-h-[44px]`, header `h-14` mobile, graphiques `h-48 sm:h-64`, colonne "Total Pts" cachée mobile
- **68 fichiers redesignés** sur l'ensemble du projet
- **Superadmin étendu** : directeurs et écoles modifiables (tous champs) via dashboard

### Corrections critiques (`fix/bugs-critiques` → mergé sur `main`)

#### Modèles et intégrité données
- **`UniqueConstraint` conditionnels** sur `SchoolClass` et `Subject` : contrainte active uniquement sur `is_active=True` → permet la réactivation d'une entité soft-deletée avec le même nom
- **`on_delete=PROTECT`** sur toutes les FK sensibles : `Note`, `Bulletin`, `BulletinLine`, `Payment`, `Student` — empêche la suppression accidentelle de données liées
- **3 migrations appliquées** : `0006_alter_schoolclass_unique_together`, `0007_fix_protect_and_unique_constraints`, idem `payments` et `students`

#### Gestion des erreurs serveur
- **`ProtectedError` géré** sur `period_delete`, `generate_periods`, `class_subject_remove` : `try/except ProtectedError` → réponse 422 avec message d'erreur en français (au lieu de crash 500)
- **`class_delete`** : garde `student_count > 0` → 422 + toast erreur bloquant; succès → toast confirmation + `HX-Trigger show-toast`
- **`non_field_errors`** affichés sur 4 formulaires : création classe, édition classe, inscription élève, paiement

#### Système de toasts unifié
- **Toast global** ajouté à `base.html` : `{% include "settings/partials/toast.html" %}` + bridge JS `showToast` (camelCase HTMX) → `show-toast` (kebab Alpine)
- **`$nextTick` → `setTimeout`** dans le store Alpine (`base.html` + `settings_base.html`) — `$nextTick` n'existe pas dans un store Alpine (propriété magique de composant uniquement)
- **Toasts sur 8 actions** : créer classe, réactiver classe, modifier classe, importer classes, inscrire élève (individuel + groupe), mettre à jour fiche élève, importer élèves
- **Paiement** : `closePanel` → `close-panel` (kebab-case), listener dédupliqué dans `dashboard.html`

#### Modal de confirmation Alpine (remplace `hx-confirm` natif)
- **`$store.confirm`** global avec `show(options)`, `confirm()`, `cancel()` — défini dans `base.html` et `settings_base.html`
- **6 boutons de suppression migrés** vers `$store.confirm.show(...)` + `htmx.ajax(...)` : classes, périodes, matières, sujets, logo
- **CSRF** : tous les `htmx.ajax()` héritent du CSRF via `hx-headers` sur `<body>`
- **`settings_base.html`** : modal et store dupliqués (standalone, n'étend pas `base.html`) + classes CSS `btn-primary/danger/secondary` en `<style>` brut (Tailwind CDN ne compile pas les `@layer components`)

#### Fermeture modals/panels (root cause HTML case-folding)
- **Root cause identifié** : les attributs HTML sont lowercasés par le navigateur → `@closePanel.window` devient `@closepanel.window` → ne matche pas l'événement `closePanel` dispatché par HTMX (CustomEvents case-sensitive en JS)
- **Fix** : tous les noms d'événements en **kebab-case** dans `HX-Trigger` ET les listeners Alpine :
  - `closePanel` → `close-panel`
  - `closeAddModal` → `close-add-modal`
  - `closeImportModal` → `close-import-modal`
  - `closeEditModal` → `close-edit-modal`
- **Suppression de tous les `hx-on::after-request`** qui fermaient les modals/panels — remplacés par `HX-Trigger` côté vue (seul mécanisme fiable)
- **`close-edit-modal`** ajouté dans `class_update` + listener dans `class_list.html` + target aligné `outerHTML` sur `#class-row-{{ id }}` dans `class_edit_modal.html` (fix double toast)
- **Message modal suppression classe dynamique** : si `student_count > 0` → modal bloquant "Suppression impossible" + `onConfirm: null` ; sinon → modal destructif normal

### Reçus V2 — style malien ASSIA (`feature/receipts-v2` → mergé)
- **Template noir/blanc style malien** `receipt_standard.html` : A5 portrait, Times New Roman, double bordure, B.P.F. box, *La Somme de* en italique, statut SOLDÉ / RESTE À PAYER / NON PAYÉ
- **`amount_to_words_fr`** dans `apps/payments/utils.py` — conversion montant FCFA en lettres françaises (22/22 tests) : règles plurielles quatre-vingts, deux cents, mille invariable
- **Contexte reçu enrichi** : `amount_words`, `date_long` (français), `school_year` (année active), `signer_title` configurable
- **`receipt_signer_title`** ajouté sur `School` (défaut "Le Caissier / Directeur") — migration `0010`
- **`primary_color` supprimé** du modèle, `AppearanceForm`, `appearance_form.html`
- **Aperçu settings** `receipt_standard_preview.html` entièrement réécrit en noir/blanc (données fictives cohérentes)
- **Champ titre signataire** dans `/settings/receipt/` avec 4 suggestions rapides (Le Directeur / Le Caissier / Le Comptable / La Directrice)
- **Panel reçu inline** (`receipt_preview_panel.html`) : header fixe + iframe PDF scrollable + footer bar indépendant
- **Footer bar** `#receipt-footer-bar` `fixed bottom-0` hors panel → évite le stacking context de `<main>` ; offset `left` dynamique via `$store.sidebar.open` (`lg:left-64` / `lg:left-16`) — safelist Tailwind ajouté
- **`Alpine.store('payments', {...})`** global : `showPanel`, `showHistory`, `showReceiptPanel` migrés depuis les variables locales → communication entre composants Alpine et contenu HTMX
- **Timeline paiements** réécriture : dots verts/rouges, cards `border-l-4` colorées, bouton "Voir le reçu" HTMX + fermeture modale historique simultanée
- **Fix N+1** `_students_qs()` : `Prefetch('payments', to_attr='active_payments')` → 1 requête au lieu de N
- **Fix X-Frame-Options** : `@xframe_options_sameorigin` sur `payment_receipt_download` → iframe PDF fonctionne
- **Fix seed demo** : `city='Bamako'`, `country='Mali'` — placeholders forms mis à jour
- **Vues ajoutées** : `receipt_preview`, `receipt_download` + 2 URLs

### QA Testing et corrections sécurité (`feature/qa-testing` → mergé)
- **21 vues settings protégées** `@director_or_staff_required` — enseignants bloqués sur toutes les routes `/settings/`
- **XSS `classes_json` corrigée** — `{{ classes_json|safe }}` → `json_script` + `JSON.parse(...)` dans `student_list.html`
- **Lien Paramètres caché aux enseignants** — desktop dropdown + mobile nav gérés avec `{% if role == 'director' or 'staff' or superuser %}`
- **Index composite `SchoolClass`** (`school`, `is_active`) — migration `0011`
- **`RuntimeError` import → 422 propre** — `_unique_access_codes` enveloppé dans try/except, retourne HX-Trigger toast au lieu d'une 500
- **Table superadmin overflow mobile** — `<div class="overflow-x-auto">` autour du tableau des écoles

### Authentification custom (`/login/`)
- **Login par numéro de téléphone** — `PhoneBackend` + `LoginForm` avec messages d'erreur précis
- **Rate limiting** : 5 échecs consécutifs → blocage 15 minutes (cache Django)
- **Logout** avec toast de confirmation de déconnexion
- **Redirection intelligente par rôle** : superuser → `/superadmin/`, director/staff → `/classes/`
- **Session** : expire après 8h d'inactivité (`SESSION_COOKIE_AGE` + `SESSION_SAVE_EVERY_REQUEST`)
- **Vrai multi-tenant** : `get_school(request)` unique source de vérité, `SchoolMiddleware` → `request.school` dans les templates
- `get_demo_school()` supprimé intégralement (27 occurrences dans 4 fichiers)

### Portail Professeur (`/teacher/`)
- **Dashboard mobile-first** avec stats (classes, élèves, absences du jour), classes filtrées par enseignant, section alertes
- **Sidebar et bottom nav dédiées** : liens Accueil / Notes / Absences / Suivi élèves, pill style iOS état actif exclusif par page
- **Accès sécurisé** : `@teacher_required`, guards 403 sur classes non-assignées, vues admin bloquées, isolation multi-tenant via `get_school(request)`
- **Absences révolutionnaires** : grille tactile tap-cycle présent → absent → retard, save atomique, redirect après save, badge "non saisies"
- **Notes ultra-rapides mobile** : clavier numérique géant, swipe matière, barre progression, `notes_mobile_input.html` partial
- **Observations élèves** : privées (visible prof seulement) vs admin (notifie le directeur), badge `obs_count`, panel slide-from-right, toggle confidentialité, filtre `is_private=False` côté admin
- **Suivi élèves en difficulté** :
  - `QuickAssessment` (oral / écrit / devoir / classe / comportement) — privé, hors bulletins
  - `services.py` : `compute_difficulty_score()` pondéré 60% notes officielles / 40% QA, `get_class_difficulty_report()` 2 SQL zéro N+1
  - Niveaux : critical (<8) / warning (<10) / watch (<12) / good (≥12)
  - Tendance : avg 3 premières vs 3 dernières évals — up / stable / down
  - Dashboard accordéons par classe, auto-ouvert si critiques
  - Vue classe : table desktop + cards mobile, filtres tabs par niveau
  - Panel éval rapide slide-from-right (même style que panel observation)
- **Modèles** : `Attendance`, `StudentObservation` (`is_private`), `QuickAssessment`
- **Bottom nav pill style iOS** : `bg-brand-blue/10 rounded-xl`, condition exclusive par `url_name`, `whitespace-nowrap`

---

## Roadmap — Prochaines étapes

### PRIORITÉ HAUTE

**1. ✅ Portail Professeur** — terminé

**2. Portail Parent** (1-2 jours)
- Voir bulletins de ses enfants
- Voir statut paiements
- Lecture seule (pas de paiement en ligne pour l'instant)

**3. Portail Élève** (3-5 jours)
- Style Duolingo
- Notes et bulletins
- Quiz et exercices
- Gamification : XP, badges, streaks

### PRIORITÉ MOYENNE

**4. Gestion Fin d'Année** (3-4 jours)
- Assistant transition annuelle (wizard)
- Promotion automatique des élèves
- Gestion redoublants et transferts
- Archivage de l'année précédente
- Rapport : promus / redoublants / transferts
- Historique élève multi-années

**5. Déploiement** (1-2 jours)
- Railway ou Render
- Objectif : avant septembre 2026 (rentrée scolaire Mali)

### PRIORITÉ BASSE (après premiers clients)

6. Notifications WhatsApp (~3 FCFA/msg via API)
7. Analytics directeur multi-années
8. Traduction arabe pour médersas
9. Portail élève avancé avec IA

---

## Dette technique à corriger

- [✅] **`DEMO_SCHOOL_ID` remplacé par `get_school(request)`** — `get_demo_school()` supprimé dans les 4 fichiers de vues

- [✅] **`LOGIN_URL` corrigé vers `accounts:login`** — PhoneBackend + LoginForm + vues en place

- [✅] **Multi-tenant réel en place** via `get_school(request)`, `SchoolMixin`, `SchoolMiddleware`

- [✅] **Tailwind CDN → build local** — `tailwind.config.js` + `npm run build:css` → `static/css/output.css`

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
