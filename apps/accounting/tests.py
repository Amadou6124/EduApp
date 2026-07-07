"""
Tests assiduité / paie vacataire.

Couvre : la contrainte « un seul émargement par (cours, date, session) », et le
calcul de la paie vacataire = Σ (heures émargées « présent » × tarif du cours).

Lancer : venv/bin/python manage.py test apps.accounting
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.db import IntegrityError, transaction

from apps.accounts.models import User, UserRole, Membership
from apps.schools.models import School, SchoolClass, Subject, ClassSubject
from apps.accounting.models import (
    EmployeeProfile, EmploymentType, VacataireRate, TeacherAttendance,
)
from apps.accounting.services import compute_vacataire_pay


class EmargementPaieTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.director = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.teacher = User.objects.create_user(
            phone_number='73000001', password='pw', role=UserRole.TEACHER, full_name='Prof',
        )
        membership = Membership.objects.create(
            user=cls.teacher, school=cls.school, role=UserRole.TEACHER, is_default=True,
        )
        cls.profile = EmployeeProfile.objects.create(
            membership=membership, employment_type=EmploymentType.VACATAIRE,
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        subject = Subject.objects.create(school=cls.school, name='Maths')
        cls.cs = ClassSubject.objects.create(
            school_class=cls.klass, subject=subject, teacher=cls.teacher, is_active=True,
        )
        # Tarif horaire du cours : 2000 FCFA/h.
        VacataireRate.objects.create(profile=cls.profile, class_subject=cls.cs, hourly_rate=Decimal('2000'))

    def _emarge(self, day, hours):
        return TeacherAttendance.objects.create(
            school=self.school, teacher=self.teacher, class_subject=self.cs,
            date=date(2026, 1, day), session='full', status='present',
            hours=Decimal(str(hours)), recorded_by=self.director,
        )

    def test_un_seul_emargement_par_cours_date_session(self):
        self._emarge(10, 3)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._emarge(10, 2)   # même (cours, date, session) → refusé

    def test_paie_vacataire_heures_x_taux(self):
        # 3h le 10, 2h le 11 = 5h × 2000 = 10 000 FCFA.
        self._emarge(10, 3)
        self._emarge(11, 2)
        pay = compute_vacataire_pay(self.school, 2026, 1)
        self.assertEqual(pay[self.teacher.id]['hours'], Decimal('5'))
        self.assertEqual(pay[self.teacher.id]['amount'], Decimal('10000'))
