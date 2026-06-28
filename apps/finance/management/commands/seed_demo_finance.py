"""
Seed de DÉMO finance pour une école — données réalistes au NOUVEAU modèle.

But : amener une école (ex. Sundiata) sur le modèle moderne (fiches + tranches datées
+ paiements alloués) avec un MIX d'états voulus, pour exercer toutes les vues finance
en état « plein ». Reproductible (graine), idempotent (purge + régénère).

Usage :
    python manage.py seed_demo_finance --school <id>
    python manage.py seed_demo_finance --school <id> --no-fee-classes 1 --seed 42

NE TOUCHE QU'À L'ÉCOLE CIBLÉE. Données de démo uniquement — jamais en prod réelle.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.schools.models import School, SchoolClass
from apps.students.models import Student, StudentEnrollment
from apps.payments.models import Payment, PaymentMethod
from apps.finance.models import (
    FeeType, FeeVariant, PaymentScheduleTemplate,
    StudentFeeAccount, FeeDebt, FeeDebtKind, Installment, PaymentAllocation,
)
from apps.finance.seeds import seed_fee_catalog
from apps.finance.services import (
    build_fee_accounts_bulk, allocate_payment, generate_subscription_installments,
    annotate_students_with_fees,
)

METHODS = [PaymentMethod.CASH, PaymentMethod.CASH, PaymentMethod.ORANGE_MONEY, PaymentMethod.WAVE]


class Command(BaseCommand):
    help = "Seed démo finance (catalogue + fiches + paiements alloués, mix d'états) sur une école."

    def add_arguments(self, parser):
        parser.add_argument('--school', type=int, required=True, help="ID de l'école cible")
        parser.add_argument('--no-fee-classes', type=int, default=1,
                            help="Nb de classes laissées SANS fiche (exerce l'état neutre 'no_fee')")
        parser.add_argument('--subscriptions', type=int, default=25,
                            help="Nb d'élèves avec un abonnement Bus (3e famille)")
        parser.add_argument('--seed', type=int, default=42, help="Graine aléatoire (reproductible)")

    def handle(self, *args, **opt):
        random.seed(opt['seed'])
        school = School.objects.filter(pk=opt['school']).first()
        if not school:
            raise CommandError(f"École #{opt['school']} introuvable.")

        collector = self._collector_for(school)
        if collector is None:
            raise CommandError("Aucun directeur/staff trouvé pour attribuer les paiements (collected_by).")

        today = timezone.now().date()

        with transaction.atomic():
            self._purge(school)
            self._set_genders(school)
            seed_fee_catalog(school)
            # Pour la démo : la tenue est obligatoire → incluse par le builder bulk (genrée).
            FeeType.objects.filter(school=school, name='Tenue').update(is_mandatory=True)

            # Classes laissées sans fiche (état neutre 'no_fee')
            no_fee_class_ids = list(
                SchoolClass.objects.filter(school=school).order_by('name')
                .values_list('id', flat=True)[:max(opt['no_fee_classes'], 0)]
            )
            enrollments = list(
                StudentEnrollment.objects
                .filter(student__school_class__school=school, status='active')
                .exclude(school_class_id__in=no_fee_class_ids)
                .select_related('student', 'school_class', 'school', 'school_year')
            )
            build_fee_accounts_bulk(enrollments)

            paid, partial, unpaid = self._generate_payments(school, collector, today)
            n_sub = self._add_subscriptions(school, collector, today, opt['subscriptions'])

        self._recap(school, no_fee_class_ids, paid, partial, unpaid, n_sub)

    # ──────────────────────────────────────────────────────────────────────────
    def _collector_for(self, school):
        from django.contrib.auth import get_user_model
        U = get_user_model()
        return (U.objects.filter(role='director', school=school).first()
                or U.objects.filter(role='staff', school=school).first()
                or U.objects.filter(role='director').first())

    def _purge(self, school):
        """Table rase finance pour l'école (enfants → parents, paiements, catalogue)."""
        PaymentAllocation.objects.filter(installment__debt__account__enrollment__school=school).delete()
        Installment.objects.filter(debt__account__enrollment__school=school).delete()
        FeeDebt.objects.filter(account__enrollment__school=school).delete()
        StudentFeeAccount.objects.filter(enrollment__school=school).delete()
        Payment.objects.filter(student__school_class__school=school).delete()
        FeeVariant.objects.filter(fee_type__school=school).delete()
        FeeType.objects.filter(school=school).delete()
        PaymentScheduleTemplate.objects.filter(school=school).delete()

    def _set_genders(self, school):
        students = list(Student.objects.filter(school_class__school=school))
        for st in students:
            st.gender = random.choice(['M', 'F'])
        Student.objects.bulk_update(students, ['gender'])

    def _pay(self, student, amount, collector, today):
        amount = int(amount)
        if amount <= 0:
            return None
        return Payment.objects.create(
            student=student, amount=amount,
            payment_date=today - timedelta(days=random.randint(5, 210)),
            payment_method=random.choice(METHODS), collected_by=collector,
        )

    def _generate_payments(self, school, collector, today):
        """Répartit les fiches en à jour / partiel / impayé, et alloue (FIFO intra-dette)."""
        accounts = (
            StudentFeeAccount.objects.filter(enrollment__school=school)
            .select_related('enrollment__student')
            .prefetch_related('debts__installments')
        )
        paid = partial = unpaid = 0
        for acc in accounts:
            student = acc.enrollment.student
            r = random.random()
            profile = 'paid' if r < 0.38 else ('partial' if r < 0.68 else 'unpaid')
            if profile == 'unpaid':
                unpaid += 1
                continue

            for debt in acc.debts.all():
                if debt.kind == FeeDebtKind.SUBSCRIPTION:
                    continue
                balance = debt.balance()
                if balance <= 0:
                    continue
                if profile == 'paid':
                    amt = balance
                else:  # partiel
                    if debt.kind == FeeDebtKind.TUITION:
                        insts = list(debt.installments.order_by('sequence'))
                        k = random.choice([1, 1, 2])  # surtout 1 tranche
                        amt = sum(int(i.amount_due) for i in insts[:k])
                    else:  # ponctuels : payés ~2 fois sur 3 en partiel
                        amt = balance if random.random() < 0.66 else 0
                p = self._pay(student, amt, collector, today)
                if p:
                    allocate_payment(p, debt)

            paid += (profile == 'paid')
            partial += (profile == 'partial')
        return paid, partial, unpaid

    def _add_subscriptions(self, school, collector, today, n):
        """Ajoute un abonnement Bus (3e famille) à n élèves ayant une fiche, + 1 mois payé."""
        bus = FeeType.objects.filter(school=school, name='Bus').first()
        if not bus or n <= 0:
            return 0
        variants = list(bus.variants.filter(is_active=True))
        if not variants:
            return 0
        accounts = list(
            StudentFeeAccount.objects.filter(enrollment__school=school)
            .select_related('enrollment__student')[:max(n * 4, n)]
        )
        random.shuffle(accounts)
        created = 0
        for acc in accounts[:n]:
            v = random.choice(variants)
            debt = FeeDebt.objects.create(
                account=acc, fee_type=bus, variant=v, kind=FeeDebtKind.SUBSCRIPTION,
                label=f'Bus — {v.label}', total_amount=v.amount, is_active=True,
            )
            insts = generate_subscription_installments(debt, n_months=1, today=today)
            # 1 mois sur 2 payé (mix payé/dû sur les abonnements)
            if insts and random.random() < 0.5:
                p = self._pay(acc.enrollment.student, insts[0].amount_due, collector, today)
                if p:
                    allocate_payment(p, debt)
            created += 1
        return created

    def _recap(self, school, no_fee_class_ids, paid, partial, unpaid, n_sub):
        st = annotate_students_with_fees(Student.objects.filter(school_class__school=school))
        from collections import Counter
        dist = Counter(s.fee_status for s in st)
        accounts = StudentFeeAccount.objects.filter(enrollment__school=school).count()
        insts = Installment.objects.filter(debt__account__enrollment__school=school).count()
        allocs = PaymentAllocation.objects.filter(installment__debt__account__enrollment__school=school).count()
        pays = Payment.objects.filter(student__school_class__school=school).count()
        self.stdout.write(self.style.SUCCESS(f"\n✓ Seed démo finance — {school.name}"))
        self.stdout.write(
            f"  fiches: {accounts} · tranches: {insts} · paiements: {pays} · allocations: {allocs} · abonnements: {n_sub}\n"
            f"  classes sans fiche: {len(no_fee_class_ids)}\n"
            f"  états élèves → payé:{dist.get('paid',0)} · partiel:{dist.get('partial',0)} · "
            f"impayé:{dist.get('unpaid',0)} · sans fiche:{dist.get('no_fee',0)}"
        )
