"""
Solde promoteur (synthèse) — NET des remises (l'argent, chiffre exact).

Prouve que « à recouvrer » du groupe soustrait bien les remises (pas seulement que la
page s'affiche). Lancer : venv/bin/python manage.py test apps.promoter
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole
from apps.schools.models import School, SchoolYear, SchoolClass, SchoolGroup
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus
from apps.finance.services import build_fee_account, create_fee_discount
from apps.finance.models import FeeDebtKind


class PromoterNetTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.promoter = User.objects.create_user(
            phone_number='76000060', password='pw', role=UserRole.PROMOTER, full_name='Promo',
        )
        cls.group = SchoolGroup.objects.create(name='Groupe', owner=cls.promoter)
        cls.school = School.objects.create(
            name='École G', short_name='EG', city='Bamako', school_type='primary', group=cls.group,
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
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
        account = build_fee_account(enr)
        tuition = account.debts.get(kind=FeeDebtKind.TUITION)
        create_fee_discount(tuition, motif='fratrie', amount=40000)   # net dû = 200 000

    def test_synthese_a_recouvrer_net(self):
        self.client.force_login(self.promoter)
        resp = self.client.get(reverse('promoter:synthese'))
        self.assertEqual(resp.status_code, 200)
        # net dû = 240 000 − 40 000 = 200 000, rien payé → à recouvrer = 200 000 (pas 240 000)
        self.assertEqual(resp.context['a_recouvrer'], Decimal('200000'))
        self.assertEqual(resp.context['schools_data'][0]['unpaid'], Decimal('200000'))
