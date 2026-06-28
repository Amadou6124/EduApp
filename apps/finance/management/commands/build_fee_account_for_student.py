"""
Commande de test (Lot 3) : construit la fiche financière d'un élève sans attendre
l'inscription enrichie (lot 4).

Usage :
    python manage.py build_fee_account_for_student --student <id>
    python manage.py build_fee_account_for_student --enrollment <id>

Affiche un récap lisible (dettes, tranches, statuts). Idempotent. Hors migration.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.students.models import Student, StudentEnrollment, EnrollmentStatus
from apps.finance.services import build_fee_account, is_returning_student


class Command(BaseCommand):
    help = "Construit (ou affiche) la fiche financière d'un élève pour son année active."

    def add_arguments(self, parser):
        parser.add_argument('--student', type=int, help="ID de l'élève")
        parser.add_argument('--enrollment', type=int, help="ID d'un StudentEnrollment précis")

    def handle(self, *args, **opts):
        enrollment = self._resolve_enrollment(opts)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Élève : {enrollment.student.full_name} — {enrollment}"
        ))
        self.stdout.write(
            f"Statut : {'ANCIEN (réinscription)' if is_returning_student(enrollment) else 'NOUVEAU'}"
        )

        account = build_fee_account(enrollment)

        self.stdout.write('')
        for kind_label, kind in (('SCOLARITÉ', 'tuition'),
                                 ('FRAIS PONCTUELS', 'one_time'),
                                 ('ABONNEMENTS', 'subscription')):
            debts = account.debts.filter(kind=kind)
            if not debts:
                continue
            self.stdout.write(self.style.HTTP_INFO(f"── {kind_label} ──"))
            for d in debts:
                flag = '' if d.is_active else '  [inactive]'
                self.stdout.write(
                    f"  • {d.label} : {d.total_amount} FCFA "
                    f"(payé {d.amount_paid()}, solde {d.balance()}, {d.status()}){flag}"
                )
                for inst in d.installments.order_by('sequence'):
                    od = ' EN RETARD' if inst.is_overdue() else ''
                    self.stdout.write(
                        f"      - {inst.label} : {inst.amount_due} FCFA "
                        f"éch. {inst.due_date} [{inst.status()}]{od}"
                    )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"TOTAL dû {account.total_due()} | payé {account.total_paid()} "
            f"| solde {account.total_balance()}"
        ))

    def _resolve_enrollment(self, opts):
        if opts.get('enrollment'):
            try:
                return StudentEnrollment.objects.select_related(
                    'student', 'school', 'school_class', 'school_year'
                ).get(pk=opts['enrollment'])
            except StudentEnrollment.DoesNotExist:
                raise CommandError(f"StudentEnrollment #{opts['enrollment']} introuvable.")

        if opts.get('student'):
            try:
                student = Student.objects.get(pk=opts['student'])
            except Student.DoesNotExist:
                raise CommandError(f"Élève #{opts['student']} introuvable.")
            enrollment = (
                StudentEnrollment.objects
                .filter(student=student, status=EnrollmentStatus.ACTIVE)
                .select_related('student', 'school', 'school_class', 'school_year')
                .order_by('-created_at')
                .first()
            )
            if enrollment is None:
                raise CommandError(
                    f"Aucun StudentEnrollment ACTIVE pour l'élève #{student.pk}. "
                    "Active une année scolaire et relance le backfill (lot 1)."
                )
            return enrollment

        raise CommandError('Précisez --student <id> ou --enrollment <id>.')
