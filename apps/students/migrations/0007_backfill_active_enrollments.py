# Generated manually — Lot 1 (module Finances) : backfill du socle temporel.
#
# But : donner à chaque élève ACTIF un StudentEnrollment de statut ACTIVE rattaché
# à l'année active de son école, afin que StudentEnrollment devienne réellement la
# source de vérité de l'inscription courante (cf. docstring du modèle).
#
# Garanties :
#   - ADDITIVE : ne modifie/supprime aucune donnée existante, ne crée que des
#     enrollments manquants.
#   - IDEMPOTENTE : on saute tout élève qui possède DÉJÀ un enrollment pour
#     (élève, année active), quel que soit son statut. Relançable sans doublon
#     (cohérent avec la contrainte unique uniq_enrollment_student_year).
#   - TOLÉRANTE : une école sans année active (is_active=True) est ignorée avec un
#     avertissement loggué — on ne plante pas la migration sur une école mal
#     configurée ; ses élèves seront rattachés plus tard, une fois l'année activée.

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# Valeur stable de EnrollmentStatus.ACTIVE. On la fige en dur plutôt que d'importer
# l'enum applicative : une data migration doit rester reproductible même si le code
# évolue. Le code 'active' fait partie du contrat de données (ne pas renommer).
STATUS_ACTIVE = 'active'


def backfill_active_enrollments(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    StudentEnrollment = apps.get_model('students', 'StudentEnrollment')
    SchoolYear = apps.get_model('schools', 'SchoolYear')
    School = apps.get_model('schools', 'School')

    total_created = 0

    for school in School.objects.all():
        # L'année active de l'école = SchoolYear.is_active=True (au plus une, garantie
        # par la contrainte unique_active_schoolyear_per_school + clean()).
        active_year = (
            SchoolYear.objects.filter(school=school, is_active=True).first()
        )
        if active_year is None:
            logger.warning(
                "[finance lot1] École #%s « %s » sans année active : élèves ignorés "
                "(aucun enrollment créé).",
                school.pk, school.name,
            )
            continue

        # Élèves de cette école ayant DÉJÀ un enrollment pour l'année active (tous
        # statuts) → on ne les retouche pas. C'est ce qui rend la migration idempotente
        # et compatible avec la contrainte d'unicité (élève, année).
        already_enrolled_ids = set(
            StudentEnrollment.objects
            .filter(school=school, school_year=active_year)
            .values_list('student_id', flat=True)
        )

        to_create = []
        active_students = (
            Student.objects
            .filter(school=school, is_active=True)
            .exclude(id__in=already_enrolled_ids)
        )
        for student in active_students:
            to_create.append(StudentEnrollment(
                student=student,
                school=school,
                # school_class = classe courante de l'élève (cache de l'inscription).
                school_class=student.school_class,
                school_year=active_year,
                status=STATUS_ACTIVE,
                # enrolled_at de l'enrollment est un DateField ; Student.enrolled_at est
                # un DateTimeField (auto_now_add) → conversion .date(), None si absent.
                enrolled_at=(
                    student.enrolled_at.date() if student.enrolled_at else None
                ),
            ))

        if to_create:
            StudentEnrollment.objects.bulk_create(to_create)
            total_created += len(to_create)
            logger.info(
                "[finance lot1] École #%s « %s » : %s enrollment(s) ACTIVE créé(s) "
                "pour l'année %s.",
                school.pk, school.name, len(to_create), active_year.name,
            )

    logger.info("[finance lot1] Backfill terminé : %s enrollment(s) créé(s) au total.",
                total_created)


def reverse_noop(apps, schema_editor):
    """Reverse volontairement NO-OP.

    On ne supprime rien au rollback : impossible de distinguer de façon fiable un
    enrollment créé par ce backfill d'un enrollment légitime créé par ailleurs
    (même couple élève/année/statut). Laisser ces lignes ACTIVE en place est sans
    danger — elles reflètent l'état réel des inscriptions. Si un nettoyage est
    nécessaire, il doit être fait explicitement à la main, pas par un rollback.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        # Dépend du schéma (champ gender + contrainte d'unicité) : on veut que la
        # contrainte uniq_enrollment_student_year existe AVANT d'insérer, pour que
        # tout doublon accidentel échoue franchement plutôt que de passer en silence.
        ('students', '0006_student_gender_enrollment_unique'),
    ]

    operations = [
        migrations.RunPython(backfill_active_enrollments, reverse_noop),
    ]
