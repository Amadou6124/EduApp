"""
Smoke test / régression : chaque écran principal rend 200 pour chaque rôle.

Le filet le plus large — il attrape les crashs de page (500) sur tous les écrans,
comme le bug dashboard (date formatée avec l'heure) qu'on a corrigé. Une école
minimale mais peuplée (année, classe, matière, élève, fiche financière, paiement).

Lancer : venv/bin/python manage.py test apps.dashboard
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole, Membership
from apps.schools.models import School, SchoolYear, SchoolClass, Period, Subject, ClassSubject, SchoolGroup
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus, StudentGuardian
from apps.finance.services import build_fee_account
from apps.payments.models import Payment


class SmokeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.period = Period.objects.create(school_year=cls.year, name='Trimestre 1', order=1)
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('244000'), max_capacity=40,
        )

        # Rôles
        cls.director = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        Membership.objects.create(user=cls.director, school=cls.school, role=UserRole.DIRECTOR, is_default=True)
        cls.teacher = User.objects.create_user(
            phone_number='73000001', password='pw', role=UserRole.TEACHER, full_name='Prof',
        )
        Membership.objects.create(user=cls.teacher, school=cls.school, role=UserRole.TEACHER, is_default=True)
        cls.parent = User.objects.create_user(
            phone_number='72000001', password='pw', role=UserRole.PARENT, full_name='Parent',
        )
        cls.promoter = User.objects.create_user(
            phone_number='76000001', password='pw', role=UserRole.PROMOTER, full_name='Promo',
        )
        group = SchoolGroup.objects.create(name='Groupe', owner=cls.promoter)
        cls.school.group = group
        cls.school.save(update_fields=['group'])

        # Matière + assignation prof, élève + inscription + fiche + un paiement.
        subject = Subject.objects.create(school=cls.school, name='Maths')
        ClassSubject.objects.create(school_class=cls.klass, subject=subject, teacher=cls.teacher, is_active=True)
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, full_name='Awa Traore',
            gender='F', tuition_fee=Decimal('244000'),
        )
        StudentGuardian.objects.create(guardian=cls.parent, student=cls.student, relationship='mère')
        enrollment = StudentEnrollment.objects.create(
            student=cls.student, school=cls.school, school_class=cls.klass,
            school_year=cls.year, status=EnrollmentStatus.ACTIVE,
        )
        build_fee_account(enrollment)
        Payment.objects.create(
            student=cls.student, amount=Decimal('15000'), payment_date=date.today(),
            payment_method='cash', collected_by=cls.director,
        )

    def _smoke(self, user, targets):
        self.client.force_login(user)
        for name, args in targets:
            with self.subTest(url=name):
                r = self.client.get(reverse(name, args=args), follow=True)
                self.assertEqual(r.status_code, 200, f'{name} a rendu {r.status_code}')

    def test_ecrans_directeur(self):
        self._smoke(self.director, [
            ('dashboard:main', []),
            ('students:list', []),
            ('students:suivi', []),
            ('students:detail', [self.student.id]),
            ('notes:dashboard', []),
            ('bulletins:main', []),
            ('payments:dashboard', []),
            ('settings:school-years', []),
            ('settings:subjects', []),
            ('settings:fees', []),
            ('settings:school-year-periods', [self.year.id]),
        ])

    def test_ecrans_enseignant(self):
        self._smoke(self.teacher, [
            ('teacher:dashboard', []),
            ('teacher:difficulty', []),
            ('teacher:students', []),
            ('teacher:student-detail', [self.student.id]),
            ('notes:dashboard', []),
        ])

    def test_ecrans_parent(self):
        self._smoke(self.parent, [
            ('parent:dashboard', []),
            ('parent:scolarite', []),
            ('parent:payments', []),
            ('parent:account', []),
            ('parent:bulletins', []),
            ('parent:annonces', []),
        ])

    def test_ecrans_promoteur(self):
        self._smoke(self.promoter, [
            ('promoter:synthese', []),
            ('promoter:ecoles', []),
            ('promoter:school-detail', [self.school.id]),
            ('promoter:finances', []),
        ])
