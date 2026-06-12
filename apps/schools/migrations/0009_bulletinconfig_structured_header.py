from django.db import migrations, models


def migrate_ministry_text(apps, schema_editor):
    """
    Migre ministry_text et republic_text (blobs libres)
    vers les champs structurés lignes 1/2/3.
    Split sur newlines. Valeurs par défaut si blob vide.
    """
    BulletinConfig = apps.get_model('schools', 'BulletinConfig')
    for cfg in BulletinConfig.objects.all():
        ministry_lines = [l.strip() for l in (cfg.ministry_text or '').split('\n') if l.strip()]
        cfg.ministry_line1 = ministry_lines[0] if len(ministry_lines) > 0 else "MINISTERE DE L'EDUCATION NATIONALE"
        cfg.ministry_line2 = ministry_lines[1] if len(ministry_lines) > 1 else ''
        cfg.ministry_line3 = ministry_lines[2] if len(ministry_lines) > 2 else ''

        republic_lines = [l.strip() for l in (cfg.republic_text or '').split('\n') if l.strip()]
        cfg.republic_line1 = republic_lines[0] if len(republic_lines) > 0 else 'REPUBLIQUE DU MALI'
        cfg.republic_line2 = republic_lines[1] if len(republic_lines) > 1 else 'UN PEUPLE - UN BUT - UNE FOI'
        cfg.save()


def migrate_ministry_text_backward(apps, schema_editor):
    """Reconstruit les blobs depuis les champs structurés (rollback)."""
    BulletinConfig = apps.get_model('schools', 'BulletinConfig')
    for cfg in BulletinConfig.objects.all():
        cfg.ministry_text = '\n'.join(
            l for l in [cfg.ministry_line1, cfg.ministry_line2, cfg.ministry_line3] if l
        )
        cfg.republic_text = '\n'.join(
            l for l in [cfg.republic_line1, cfg.republic_line2] if l
        )
        cfg.save()


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0008_education_level_mali'),
    ]

    operations = [
        # 1. Ajouter les nouveaux champs structurés
        migrations.AddField(
            model_name='bulletinconfig',
            name='ministry_line1',
            field=models.CharField(blank=True, default='', max_length=200,
                                   verbose_name="ministère — ligne 1"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='ministry_line2',
            field=models.CharField(blank=True, default='', max_length=200,
                                   verbose_name="ministère — ligne 2 (ex: Académie)"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='ministry_line3',
            field=models.CharField(blank=True, default='', max_length=200,
                                   verbose_name="ministère — ligne 3 (ex: CAP)"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='republic_line1',
            field=models.CharField(blank=True, default='', max_length=200,
                                   verbose_name="république — ligne 1"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='republic_line2',
            field=models.CharField(blank=True, default='', max_length=200,
                                   verbose_name="république — ligne 2 (devise)"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='bulletin_title',
            field=models.CharField(blank=True, default='RELEVE DE NOTES', max_length=200,
                                   verbose_name="titre du bulletin"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='show_annual_averages',
            field=models.BooleanField(default=False,
                                      verbose_name="afficher les moyennes des autres trimestres"),
        ),
        migrations.AddField(
            model_name='bulletinconfig',
            name='show_last_average',
            field=models.BooleanField(default=False,
                                      verbose_name="afficher la moyenne du dernier"),
        ),
        # 2. Migrer les données depuis les anciens blobs
        migrations.RunPython(
            migrate_ministry_text,
            migrate_ministry_text_backward,
        ),
        # 3. Supprimer les anciens blobs (données déjà migrées)
        migrations.RemoveField(model_name='bulletinconfig', name='ministry_text'),
        migrations.RemoveField(model_name='bulletinconfig', name='republic_text'),
    ]
