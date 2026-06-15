# Backfill ciblé Équipe — multi-école.
#
# L'ancien `team_member_create` ne posait que le FK `User.school` sans créer de
# Membership. Cette migration garantit qu'aucun membre d'équipe legacy
# (teacher/staff rattaché par `User.school`) ne disparaisse quand les vues Équipe
# passent à la lecture par `Membership`.
#
# Additive et idempotente (get_or_create) : rejouable sans doublon.
# `0004` couvre déjà ce backfill globalement ; on le re-sécurise ici de façon
# explicite pour les rôles d'équipe. Réversible (reverse = noop : on ne détruit
# aucune donnée au rollback).

from django.db import migrations


def backfill_team_memberships(apps, schema_editor):
    """Crée une Membership pour chaque teacher/staff rattaché par `User.school`."""
    User = apps.get_model('accounts', 'User')
    Membership = apps.get_model('accounts', 'Membership')

    team_users = User.objects.filter(
        role__in=['teacher', 'staff'],
        school__isnull=False,
    ).select_related('school')

    for user in team_users:
        # is_default seulement si l'utilisateur n'a encore aucune école par défaut.
        has_default = Membership.objects.filter(user=user, is_default=True).exists()
        Membership.objects.get_or_create(
            user=user,
            school=user.school,
            defaults={
                'role': user.role,
                'job_title': getattr(user, 'job_title', '') or '',
                'is_default': not has_default,
                'is_active': user.is_active,
            },
        )


def noop(apps, schema_editor):
    """Reverse : aucune destruction de données."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_add_can_record_emargement'),
    ]

    operations = [
        migrations.RunPython(backfill_team_memberships, noop),
    ]
