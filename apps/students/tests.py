"""
Tests des inscriptions (StudentEnrollment) — la colonne vertébrale annuelle.

Couvre : création de l'inscription de l'année active, idempotence (jamais de
doublon), garde-fou « pas d'année active » (None, jamais un 500), et la contrainte
d'unicité (une seule inscription par élève et par année).

Lancer : venv/bin/python manage.py test apps.students
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.db import IntegrityError, transaction

from apps.schools.models import School, SchoolYear, SchoolClass
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus
from apps.students.services import ensure_active_enrollment


class EnrollmentTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, full_name='Awa Traore',
            tuition_fee=Decimal('100000'),
        )

    def _active_year(self):
        return SchoolYear.objects.create(
            school=self.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )

    def test_inscription_creee_pour_annee_active(self):
        year = self._active_year()
        enr = ensure_active_enrollment(self.student)
        self.assertIsNotNone(enr)
        self.assertEqual(enr.school_year_id, year.id)
        self.assertEqual(enr.status, EnrollmentStatus.ACTIVE)

    def test_inscription_idempotente(self):
        self._active_year()
        e1 = ensure_active_enrollment(self.student)
        e2 = ensure_active_enrollment(self.student)
        self.assertEqual(e1.id, e2.id)   # même inscription, pas de doublon
        self.assertEqual(StudentEnrollment.objects.filter(student=self.student).count(), 1)

    def test_sans_annee_active_pas_inscription(self):
        # Aucune année active → None + aucune inscription créée (jamais un 500).
        self.assertIsNone(ensure_active_enrollment(self.student))
        self.assertEqual(StudentEnrollment.objects.filter(student=self.student).count(), 0)

    def test_une_seule_inscription_par_annee(self):
        year = self._active_year()
        StudentEnrollment.objects.create(
            student=self.student, school=self.school, school_class=self.klass,
            school_year=year, status=EnrollmentStatus.ACTIVE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentEnrollment.objects.create(
                    student=self.student, school=self.school, school_class=self.klass,
                    school_year=year, status=EnrollmentStatus.ACTIVE,
                )
