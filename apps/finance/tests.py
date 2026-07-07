"""
Tests des chemins financiers critiques (l'argent — zéro erreur tolérée).

Couvre : génération des frais à l'inscription, découpage exact de la scolarité en
tranches (jamais un franc perdu), tenue automatique par genre, et l'allocation des
paiements (FIFO, jamais de sur-allocation, jamais entre familles de dettes).

Lancer : venv/bin/python manage.py test apps.finance
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User, UserRole
from apps.schools.models import School, SchoolYear, SchoolClass
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus
from apps.finance.models import FeeType, FeeVariant, FeeCategory, AppliesTo, FeeDebtKind
from apps.finance.services import build_fee_account, allocate_payment
from apps.payments.models import Payment


class FinanceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.director = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('244000'), max_capacity=40,
        )
        # Élève FILLE (pour tester la tenue auto par genre).
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, full_name='Awa Traore',
            gender='F', tuition_fee=Decimal('244000'),
        )
        cls.enrollment = StudentEnrollment.objects.create(
            student=cls.student, school=cls.school, school_class=cls.klass,
            school_year=cls.year, status=EnrollmentStatus.ACTIVE,
        )

        # Catalogue : Inscription (simple, obligatoire) + Tenue (à variantes par genre).
        cls.inscription_fee = FeeType.objects.create(
            school=cls.school, name='Inscription', category=FeeCategory.ONE_TIME,
            default_amount=Decimal('15000'), is_mandatory=True, applies_to=AppliesTo.ALL,
        )
        cls.tenue_fee = FeeType.objects.create(
            school=cls.school, name='Tenue', category=FeeCategory.ONE_TIME,
            is_mandatory=True, has_variants=True, is_gender_based=True, applies_to=AppliesTo.ALL,
        )
        FeeVariant.objects.create(fee_type=cls.tenue_fee, label='Fille', amount=Decimal('6000'), gender_key='F')
        FeeVariant.objects.create(fee_type=cls.tenue_fee, label='Garçon', amount=Decimal('5000'), gender_key='M')

        # Génère la fiche (scolarité + obligatoires). Gabarit Trimestriel (3) auto-provisionné.
        cls.account = build_fee_account(cls.enrollment)

    def _tuition(self):
        return self.account.debts.get(kind=FeeDebtKind.TUITION)

    def _pay(self, amount):
        return Payment.objects.create(
            student=self.student, amount=Decimal(amount), payment_date=date.today(),
            payment_method='cash', collected_by=self.director,
        )

    # ── Génération + découpage ─────────────────────────────────
    def test_scolarite_decoupee_sans_perte_de_franc(self):
        installs = list(self._tuition().installments.order_by('sequence'))
        amounts = [i.amount_due for i in installs]
        self.assertEqual(len(installs), 3)                                  # gabarit Trimestriel
        self.assertEqual(amounts, [Decimal('81334'), Decimal('81333'), Decimal('81333')])
        self.assertEqual(sum(amounts), Decimal('244000'))                   # somme EXACTE

    def test_tenue_auto_selon_le_genre(self):
        # Élève fille → tenue = variante Fille (6000), pas Garçon (5000).
        tenue_debt = self.account.debts.get(fee_type=self.tenue_fee)
        self.assertEqual(tenue_debt.total_amount, Decimal('6000'))

    def test_inscription_obligatoire_generee(self):
        insc = self.account.debts.get(fee_type=self.inscription_fee)
        self.assertEqual(insc.total_amount, Decimal('15000'))

    # ── Allocation ─────────────────────────────────────────────
    def test_allocation_fifo(self):
        # 50 000 sur la scolarité → remplit la tranche 1 d'abord.
        allocate_payment(self._pay('50000'), self._tuition())
        t1, t2, _ = self._tuition().installments.order_by('sequence')
        self.assertEqual(t1.amount_allocated(), Decimal('50000'))
        self.assertEqual(t1.balance(), Decimal('31334'))    # 81334 - 50000
        self.assertEqual(t2.amount_allocated(), Decimal('0'))  # tranche 2 intacte

    def test_jamais_de_sur_allocation(self):
        # Payer 300 000 sur une scolarité de 244 000 → n'alloue que 244 000.
        allocate_payment(self._pay('300000'), self._tuition())
        total = sum(i.amount_allocated() for i in self._tuition().installments.all())
        self.assertEqual(total, Decimal('244000'))

    def test_jamais_entre_familles(self):
        # Payer la scolarité ne doit JAMAIS toucher l'inscription.
        allocate_payment(self._pay('50000'), self._tuition())
        insc = self.account.debts.get(fee_type=self.inscription_fee)
        self.assertEqual(insc.installments.first().amount_allocated(), Decimal('0'))
