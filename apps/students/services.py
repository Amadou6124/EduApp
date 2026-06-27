"""
Services du domaine élèves.

ensure_active_enrollment : crée (ou récupère) le StudentEnrollment ACTIVE d'un élève
pour l'année active de son école. C'est la FONDATION du lot 4 : sans enrollment, la
fiche financière (apps.finance) ne peut s'accrocher à rien. À appeler dans TOUS les
flux de création d'élève (unitaire, groupe, import).
"""
from datetime import date


def ensure_active_enrollment(student):
    """
    Retourne le StudentEnrollment ACTIVE de `student` pour l'année active de l'école.

    - Année active = SchoolYear.is_active=True (au plus une, garantie lot 1).
    - get_or_create sur (student, school_year) → respecte la contrainte unique
      conditionnelle du lot 1, jamais de doublon (idempotent : ré-inscrire ne duplique pas).
    - Si l'école n'a PAS d'année active : retourne None (le caller affiche un message
      exploitable). On ne lève pas d'exception pour ne pas transformer une école mal
      configurée en erreur 500.
    """
    from apps.schools.models import SchoolYear
    from .models import StudentEnrollment, EnrollmentStatus

    active_year = (
        SchoolYear.objects.filter(school=student.school, is_active=True).first()
    )
    if active_year is None:
        return None

    enrollment, _created = StudentEnrollment.objects.get_or_create(
        student=student,
        school_year=active_year,
        defaults=dict(
            school=student.school,
            school_class=student.school_class,
            status=EnrollmentStatus.ACTIVE,
            # enrolled_at de l'enrollment est un DateField ; Student.enrolled_at est un
            # DateTimeField (auto_now_add) → conversion .date(), repli sur aujourd'hui.
            enrolled_at=(student.enrolled_at.date() if student.enrolled_at else date.today()),
        ),
    )
    return enrollment


def has_active_year(school):
    """Raccourci : l'école a-t-elle une année scolaire active ? (garde-fou inscription)."""
    from apps.schools.models import SchoolYear
    return SchoolYear.objects.filter(school=school, is_active=True).exists()
