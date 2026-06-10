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
│   ├── schools/        → School, SchoolClass
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
| `is_active` | BooleanField(default=True) |
| `created_at` / `updated_at` | DateTimeField |

Méthodes : `get_student_count()` (utilise annotation `student_count` si disponible → évite N+1), `is_full()`
Contrainte : `unique_together = [('school', 'name')]`

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
- **Isolation multi-tenant** : tous les `get_object_or_404` filtrent `school=get_demo_school()`
- **Auth** : `@login_required` sur les 11 vues schools, `@superadmin_required` sur superadmin

---

## Prochaines étapes dans l'ordre

1. **Inscription élèves** — 3 modes : individuel rapide, import CSV, saisie par groupe
2. **Paiements + reçus PDF** — saisie paiement, reçu PDF généré, historique par élève
3. **Bulletins PDF** — avec zones variables, header école, logo
4. **Login custom + vrai multi-tenant** — page login téléphone, `get_demo_school()` → `request.user.school`
5. **Portail professeur** — liste classes, saisie notes/absences
6. **Portail élève** — style Duolingo, notes, bulletins, solde
7. **Portail parent** — bulletin, solde, paiement Orange Money

---

## Dette technique à corriger

- [ ] **Remplacer `DEMO_SCHOOL_ID` par `request.user.school`** dans `get_demo_school()` (`apps/schools/views.py`)
  → À faire quand le login custom sera construit (`apps/accounts/views.py`)

- [ ] **Remplacer `LOGIN_URL = '/admin/login/'`** par `accounts:login` dans `config/settings.py`
  → À faire quand la page de login custom sera créée

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
