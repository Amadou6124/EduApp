from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0003_fix_protect_and_unique_constraints'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE payments_payment DROP COLUMN IF EXISTS payment_type;",
            reverse_sql="ALTER TABLE payments_payment ADD COLUMN payment_type VARCHAR(50) NOT NULL DEFAULT 'scolarite';",
        ),
    ]
