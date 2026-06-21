# ÉTAPE 1 — Nettoyage complet DB + Superadmin
# Exécuter : python manage.py shell < scripts/seed/step1_cleanup_superadmin.py
#
# ⚠  DESTRUCTIF — efface toutes les données existantes
# Résultat : DB vide + superadmin (70000000 / admin123)

from django.db import connection
from apps.accounts.models import User

# ── Nettoyage total ────────────────────────────────────────────────────────
# TRUNCATE multi-tables en une seule commande → gère les FK circulaires
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename != 'django_migrations'
        ORDER BY tablename
    """)
    tables = [row[0] for row in cursor.fetchall()]

    if tables:
        table_list = ', '.join(f'"{t}"' for t in tables)
        cursor.execute(f'TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE')

print(f'✓ {len(tables)} tables nettoyées (TRUNCATE ... RESTART IDENTITY CASCADE)')

# ── Superadmin ─────────────────────────────────────────────────────────────
admin = User.objects.create_superuser(
    phone_number='70000000',
    password='admin123',
    full_name='Admin EduApp',
)
print(f'✓ Superadmin : {admin.phone_number} / admin123')
print(f'  is_superuser={admin.is_superuser} | role={admin.role}')
