from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0009_bulletinconfig_structured_header'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='school',
            name='primary_color',
        ),
        migrations.AddField(
            model_name='school',
            name='receipt_signer_title',
            field=models.CharField(
                blank=True,
                default='Le Caissier / Directeur',
                max_length=100,
                verbose_name='titre du signataire',
            ),
        ),
    ]
