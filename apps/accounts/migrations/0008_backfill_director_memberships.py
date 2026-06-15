# Backfill Directeurs — multi-école.
#
# Les backfills 0004/0007 n'ont migré que les rôles teacher/staff. Les directeurs
# créés en legacy (FK `User.school`, sans Membership de leur propre école) se
# retrouvaient sans appartenance pour leur direction : `get_school` les faisait
# défaut sur une AUTRE école (ex : une école où ils sont staff), le bouton de
# switch disparaissait (1 seule membership) et `/switch-school/` vers leur école
# renvoyait 403.
#
# Cette migration crée la Membership `director` manquante et désigne l'école du
# directeur comme école par défaut (is_default), en basculant l'éventuel défaut
# existant pour respecter la contrainte partielle `uniq_default_membership_user`.
#
# Additive et idempotente (skip si la Membership existe déjà). Réversible
# (reverse = noop : aucune destruction de données au rollback).

from django.db import migrations


def backfill_director_memberships(apps, schema_editor):
    """Crée une Membership director (école = défaut) pour chaque directeur legacy."""
    User = apps.get_model('accounts', 'User')
    Membership = apps.get_model('accounts', 'Membership')

    directors = (
        User.objects
        .filter(role='director', school__isnull=False)
        .select_related('school')
    )
    for d in directors:
        if Membership.objects.filter(user=d, school=d.school).exists():
            continue  # déjà rattaché → rien à faire (idempotent)

        # L'école du directeur devient son défaut : retirer d'abord le défaut
        # existant (contrainte uniq_default_membership_user : un seul par user).
        Membership.objects.filter(user=d, is_default=True).update(is_default=False)
        Membership.objects.create(
            user=d,
            school=d.school,
            role='director',
            job_title=getattr(d, 'job_title', '') or '',
            is_default=True,
            is_active=d.is_active,
        )


def noop(apps, schema_editor):
    """Reverse : aucune destruction de données."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_backfill_team_memberships'),
    ]

    operations = [
        migrations.RunPython(backfill_director_memberships, noop),
    ]
