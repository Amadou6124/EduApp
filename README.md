# EduApp

Plateforme de **gestion scolaire** pour le **Mali** (enseignement **Fondamental + Secondaire**, K-12).
Un seul outil pour la scolarité, les finances, les notes/bulletins, l'assiduité, et des espaces dédiés
**directeur · enseignant · parent · promoteur**.

## Fonctionnalités

- **Scolarité** : années scolaires, **périodes par cycle** (compositions au fondamental, trimestres au
  secondaire, surcharge par classe), classes, matières, élèves (création + import Excel).
- **Finances** : catalogue de frais (variantes, tenue par genre), **scolarité en tranches** (gabarits),
  échéancier daté, encaissement au guichet + reçus PDF, liste des impayés, recouvrement.
- **Pédagogie** : notes (devoir/composition), **bulletins PDF** (moyenne, rang, appréciation), suivi précoce
  des élèves en difficulté.
- **Assiduité** : émargement enseignants, absences/retards.
- **Comptabilité** : dépenses, paie (permanent / vacataire à l'heure).
- **Portails** : parent (scolarité, paiements, bulletins), promoteur (net + P&L multi-écoles), enseignant.

## Stack

Django 5.1 · PostgreSQL · Tailwind CSS · Alpine.js · HTMX · WhiteNoise · WeasyPrint (PDF).

## Installation locale

```bash
git clone <repo> && cd EduApp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # puis renseigner SECRET_KEY, DB_*, etc.
python manage.py migrate
python manage.py runserver
```

CSS (si modification des templates) :
```bash
npm install
npm run build:css               # régénère static/css/output.css (purgé)
```

## Déploiement (production)

Le code est **prêt pour un hébergement managé** (Render/Heroku) : `Procfile`, `build.sh`, `runtime.txt`,
`render.yaml`, config pilotée par variables d'environnement, support `DATABASE_URL`, Sentry conditionnel.

➡️ Suivre la **checklist go-live** : [`docs/go-live-checklist.md`](docs/go-live-checklist.md).

## Structure

```
apps/
  schools/      écoles, classes, années, périodes, matières, bulletins, paramètres
  students/     élèves, inscriptions, import, suivi
  finance/      frais, tranches, échéancier, allocations de paiement
  payments/     encaissement, reçus, impayés
  teachers/     portail enseignant, notes, émargement, difficulté
  accounting/   dépenses, paie, émargement
  parent/       portail parent
  promoter/     portail promoteur (multi-écoles)
  dashboard/    tableau de bord directeur
  accounts/     comptes, rôles, équipe, permissions
  notifications, lessons, student_learning, core
config/         settings, urls, wsgi
templates/  static/  docs/
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — référence projet
- [`docs/roadmap-post-demo.md`](docs/roadmap-post-demo.md) — évolutions priorisées + backlog
- [`docs/go-live-checklist.md`](docs/go-live-checklist.md) — mise en production
- [`docs/chantier-passage-annee.md`](docs/chantier-passage-annee.md) — plan du passage d'année (à venir)
- [`docs/chantier-periodes-par-cycle.md`](docs/chantier-periodes-par-cycle.md) — chantier périodes (fait)
- [`docs/archive/`](docs/archive/) — mémoire des chantiers terminés (finance, multi-école, comptabilité, portail élève)
