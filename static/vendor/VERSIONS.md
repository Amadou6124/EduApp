# Assets vendor (self-hostés)

Téléchargés via `python manage.py vendor_assets` (versions figées).
Raisons : perf 3G Mali · fiabilité (zéro dépendance CDN) · fondation PWA.

| Asset | Version | Source | Date |
|-------|---------|--------|------|
| htmx  | 2.0.4   | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js | 2026-06-16 |
| alpine| 3.15.12 | https://unpkg.com/alpinejs@3.15.12/dist/cdn.min.js | 2026-06-16 |
| lucide| 1.20.0  | https://unpkg.com/lucide@1.20.0/dist/umd/lucide.min.js | 2026-06-16 |
| chartjs| 4.4.1  | https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js | 2026-06-16 |

<!-- NB : lucide @latest = legacy 1.20.0 (2021). Modernisation 0.577.x = tâche dédiée future. -->
<!-- fonts Manrope : étape 4 à venir -->
<!-- Chart.js 4.4.1 (cdnjs, bilan/dashboard accounting) : self-hosté 2026-06-16 -->

