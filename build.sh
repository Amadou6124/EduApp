#!/usr/bin/env bash
# Étape de build en production (à mettre dans « Build Command » sur Render,
# ou à lancer en CI avant le déploiement).
set -o errexit   # stoppe au premier échec

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
