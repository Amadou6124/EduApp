from django.db import migrations, models


LEVEL_MAP = {
    'primary':    'fondamental_1',
    'middle':     'fondamental_2',
    'high':       'secondaire_gen',
    'university': 'superieur',
}


def migrate_levels_forward(apps, schema_editor):
    SchoolClass = apps.get_model('schools', 'SchoolClass')
    for old, new in LEVEL_MAP.items():
        SchoolClass.objects.filter(level=old).update(level=new)


def migrate_levels_backward(apps, schema_editor):
    SchoolClass = apps.get_model('schools', 'SchoolClass')
    for old, new in LEVEL_MAP.items():
        SchoolClass.objects.filter(level=new).update(level=old)


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0007_fix_protect_and_unique_constraints'),
    ]

    operations = [
        # 1. Migrer les données AVANT de changer les choices
        migrations.RunPython(
            migrate_levels_forward,
            migrate_levels_backward,
        ),
        # 2. Mettre à jour le champ (choices sont metadata Django, pas SQL)
        migrations.AlterField(
            model_name='schoolclass',
            name='level',
            field=models.CharField(
                verbose_name='niveau',
                max_length=20,
                choices=[
                    ('prescolaire',    'Préscolaire'),
                    ('fondamental_1',  'Fondamental 1er Cycle'),
                    ('fondamental_2',  'Fondamental 2ème Cycle'),
                    ('secondaire_gen', 'Secondaire Général'),
                    ('secondaire_pro', 'Secondaire Professionnel'),
                    ('superieur',      'Enseignement Supérieur'),
                ],
            ),
        ),
    ]
