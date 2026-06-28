# Assets vendor (self-hostés)

Téléchargés via `python manage.py vendor_assets` (versions figées).
Raisons : perf 3G Mali · fiabilité (zéro dépendance CDN) · fondation PWA.

| Asset | Version | Source | Date |
|-------|---------|--------|------|
| htmx  | 2.0.4   | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js | 2026-06-16 |
| alpine| 3.15.12 | https://unpkg.com/alpinejs@3.15.12/dist/cdn.min.js | 2026-06-16 |
| lucide| 1.20.0  | https://unpkg.com/lucide@1.20.0/dist/umd/lucide.min.js | 2026-06-16 |
| chartjs| 4.4.1  | https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js | 2026-06-16 |
| manrope| v20    | https://fonts.gstatic.com/s/manrope/v20/ (latin woff2 variable, 24 Ko) | 2026-06-16 |
| space-grotesk | v22 | https://fonts.gstatic.com/s/spacegrotesk/v22/ (latin woff2, wght 700, 13 Ko) — wordmark nom d'école | 2026-06-28 |

<!-- NB versions Lucide (piège de versionnage) : la série 0.x est l'ANCIENNE (pré-1.0, ≤ mars 2026). Lucide est passé en 1.0 stable le 2026-03-23 ; la 1.x est la ligne MODERNE actuelle (1.20.0 = 2026-06-16 ; latest 1.22.0 = 2026-06-28). Donc 1.20.0 est À JOUR — ne PAS « downgrader » vers 0.x. API inchangée : data-lucide + lucide.createIcons(). -->
<!-- Manrope : police variable — 1 woff2 couvre wght 400-800, sous-ensemble latin suffit pour fr/Mali -->
<!-- Chart.js 4.4.1 (cdnjs, bilan/dashboard accounting) : self-hosté 2026-06-16 -->

