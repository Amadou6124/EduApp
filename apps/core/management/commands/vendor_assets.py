"""Télécharge les assets front (vendor) en versions FIGÉES pour self-hosting.

Pourquoi : perf 3G Mali, fiabilité (zéro dépendance CDN), fondation PWA.
Idempotent (réécrit), rejouable. Étendu asset par asset (htmx → alpine → lucide → fonts).
"""
import hashlib
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

VENDOR_DIR = Path(settings.BASE_DIR) / 'static' / 'vendor'

# Versions figées — à étendre aux étapes suivantes (alpine, lucide, fonts).
ASSETS = [
    {
        'name':    'htmx',
        'version': '2.0.4',
        'url':     'https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js',
        'dest':    'htmx/htmx.min.js',
    },
    {
        'name':    'alpine',
        'version': '3.15.12',
        'url':     'https://unpkg.com/alpinejs@3.15.12/dist/cdn.min.js',
        'dest':    'alpine/alpine.min.js',
    },
    {
        # NB : @latest pointe sur la legacy 1.20.0 (2021) ; modernisation 0.577.x = tâche dédiée.
        'name':    'lucide',
        'version': '1.20.0',
        'url':     'https://unpkg.com/lucide@1.20.0/dist/umd/lucide.min.js',
        'dest':    'lucide/lucide.min.js',
    },
    {
        'name':    'chartjs',
        'version': '4.4.1',
        'url':     'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
        'dest':    'chartjs/chart.umd.min.js',
    },
    {
        # Police variable : 1 woff2 couvre wght 400-800, sous-ensemble latin (suffisant pour fr/Mali).
        'name':    'manrope',
        'version': 'v20',
        'url':     'https://fonts.gstatic.com/s/manrope/v20/xn7gYHE41ni1AdIRggexSg.woff2',
        'dest':    'fonts/manrope/manrope-latin.woff2',
    },
]


class Command(BaseCommand):
    help = "Télécharge les assets vendor (versions figées) dans static/vendor/."

    def handle(self, *args, **options):
        for a in ASSETS:
            dest = VENDOR_DIR / a['dest']
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f"↓ {a['name']} {a['version']} — {a['url']}")
            resp = requests.get(a['url'], timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            sha = hashlib.sha256(resp.content).hexdigest()
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ {a['dest']} — {len(resp.content) // 1024} Ko — sha256:{sha[:16]}…"
            ))
        self.stdout.write(self.style.SUCCESS("Assets vendor à jour."))
