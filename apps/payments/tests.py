"""
Solde du dashboard Paiements — NET des remises (l'argent, chiffre exact).

Prouve que _compute_stats soustrait bien les remises du solde restant (pas seulement
que la page s'affiche). Lancer : venv/bin/python manage.py test apps.payments
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User, UserRole
from apps.schools.models import School, SchoolYear, SchoolClass
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus
from apps.finance.services import build_fee_account, allocate_payment, create_fee_discount
from apps.finance.models import FeeDebtKind
from apps.payments.models import Payment
from apps.payments.views import _compute_stats, _dashboard_accounts


class DashboardNetTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École P', short_name='EP', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.director = User.objects.create_user(
            phone_number='70000060', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('240000'), max_capacity=40,
        )
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, first_name='Awa', last_name='T',
            gender='F', tuition_fee=Decimal('240000'),
        )
        enr = StudentEnrollment.objects.create(
            student=cls.student, school=cls.school, school_class=cls.klass,
            school_year=cls.year, status=EnrollmentStatus.ACTIVE,
        )
        cls.account = build_fee_account(enr)

    def _tuition(self):
        return self.account.debts.get(kind=FeeDebtKind.TUITION)

    def test_solde_restant_net_des_remises(self):
        # Payé 100 000, remise 40 000 → net dû = 240 000 − 40 000 = 200 000 ; solde = 100 000.
        p = Payment.objects.create(
            student=self.student, amount=Decimal('100000'), payment_date=date.today(),
            payment_method='cash', collected_by=self.director,
        )
        allocate_payment(p, self._tuition())
        create_fee_discount(self._tuition(), motif='social', amount=40000)
        stats = _compute_stats(self.school, _dashboard_accounts(self.school))
        self.assertEqual(stats['solde_restant'], Decimal('100000'))   # net, pas 140 000
