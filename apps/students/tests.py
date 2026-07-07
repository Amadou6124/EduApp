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
from django.utils import timezone

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


class StudentIdentityTests(TestCase):
    """Identité élève : Nom/Prénom séparés + full_name auto + matricule (auto, unique
    par école, immuable, modifiable). Voir apps/students/models.py."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École A', short_name='EA', city='Bamako', school_type='primary',
        )
        cls.school2 = School.objects.create(
            name='École B', short_name='EB', city='Bamako', school_type='primary',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.klass2 = SchoolClass.objects.create(
            school=cls.school2, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )

    def _make(self, school, klass, **kw):
        kw.setdefault('tuition_fee', Decimal('0'))
        return Student.objects.create(school=school, school_class=klass, **kw)

    def test_full_name_recompose_depuis_prenom_nom(self):
        s = self._make(self.school, self.klass, first_name='Awa', last_name='Traoré')
        self.assertEqual(s.full_name, 'Awa Traoré')   # Prénom Nom

    def test_matricule_auto_format_et_sequence(self):
        year = timezone.now().year
        s1 = self._make(self.school, self.klass, first_name='A', last_name='X')
        s2 = self._make(self.school, self.klass, first_name='B', last_name='Y')
        self.assertEqual(s1.matricule, f'{year}-0001')
        self.assertEqual(s2.matricule, f'{year}-0002')

    def test_matricule_immuable(self):
        s = self._make(self.school, self.klass, first_name='A', last_name='X')
        mat = s.matricule
        s.first_name = 'Autre'
        s.save()
        self.assertEqual(s.matricule, mat)   # inchangé (passage/redoublement)

    def test_matricule_unique_par_ecole(self):
        year = timezone.now().year
        a = self._make(self.school,  self.klass,  first_name='A', last_name='X')
        b = self._make(self.school2, self.klass2, first_name='B', last_name='Y')
        # Deux écoles peuvent avoir chacune AAAA-0001 sans conflit (série par tenant).
        self.assertEqual(a.matricule, f'{year}-0001')
        self.assertEqual(b.matricule, f'{year}-0001')

    def test_matricule_officiel_non_ecrase(self):
        # Un matricule fourni (officiel) est conservé, pas remplacé par l'auto.
        s = self._make(self.school, self.klass, first_name='A', last_name='X',
                       matricule='MEN-2026-999')
        self.assertEqual(s.matricule, 'MEN-2026-999')

    def test_chemin_herite_full_name_seul(self):
        # Un chemin ne passant que full_name (seed/import) dérive Prénom/Nom + matricule.
        s = self._make(self.school, self.klass, full_name='Bakary Coulibaly')
        self.assertEqual(s.first_name, 'Bakary')
        self.assertEqual(s.last_name, 'Coulibaly')
        self.assertTrue(s.matricule)

    def test_formulaire_date_naissance_obligatoire(self):
        from apps.students.forms import StudentCreateForm
        form = StudentCreateForm(
            data={'school_class': self.klass.id, 'last_name': 'X',
                  'first_name': 'A', 'gender': 'F'},
            school=self.school,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('date_of_birth', form.errors)
