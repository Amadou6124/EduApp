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


class EdtDerivedHoursTests(TestCase):
    """La durée d'une séance vient de l'EMPLOI DU TEMPS (somme des créneaux du jour),
    sauf heures tapées. Aucune coupure matin/après-midi, aucun ×2 : le créneau porte
    ses vraies heures (journée continue, cours du soir…). Repli : duration_hours."""

    @classmethod
    def setUpTestData(cls):
        from datetime import time
        from apps.schools.models import SchoolYear, CourseSlot
        cls.CourseSlot = CourseSlot
        cls.time = time
        cls.school = School.objects.create(
            name='École EDT', short_name='EE', city='Bamako', school_type='secondary',
        )
        cls.director = User.objects.create_user(
            phone_number='74000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.teacher = User.objects.create_user(
            phone_number='74000002', password='pw', role=UserRole.TEACHER, full_name='Prof V',
        )
        membership = Membership.objects.create(
            user=cls.teacher, school=cls.school, role=UserRole.TEACHER, is_default=True,
        )
        cls.profile = EmployeeProfile.objects.create(
            membership=membership, employment_type=EmploymentType.VACATAIRE,
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='9A', level='fondamental_2',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        subject = Subject.objects.create(school=cls.school, name='Maths')
        cls.cs = ClassSubject.objects.create(
            school_class=cls.klass, subject=subject, teacher=cls.teacher, is_active=True,
        )  # duration_hours défaut = 2h (le dernier filet)
        VacataireRate.objects.create(profile=cls.profile, class_subject=cls.cs, hourly_rate=Decimal('2000'))
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 9, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        # 2026-01-12 est un LUNDI (weekday 0).
        cls.lundi = date(2026, 1, 12)

    def _slot(self, start, end, day=0):
        return self.CourseSlot.objects.create(
            class_subject=self.cs, school_year=self.year, day=day,
            start_time=self.time(*start), end_time=self.time(*end),
        )

    def _emarge(self, d, hours=None, session='morning', status='present'):
        return TeacherAttendance.objects.create(
            school=self.school, teacher=self.teacher, class_subject=self.cs,
            date=date(2026, 1, d), session=session, status=status,
            hours=(Decimal(str(hours)) if hours is not None else None),
            recorded_by=self.director,
        )

    def _hours(self):
        return compute_vacataire_pay(self.school, 2026, 1).get(self.teacher.id, {}).get('hours')

    def test_map_somme_les_creneaux_du_jour(self):
        from apps.accounting.services import _slot_hours_map
        self._slot((8, 0), (10, 0))     # 2h
        self._slot((14, 0), (15, 0))    # 1h le même lundi
        m = _slot_hours_map(self.school, 2026, 1)
        self.assertEqual(m[(self.cs.id, 0)], Decimal('3'))

    def test_duree_vient_du_creneau(self):
        self._slot((8, 0), (10, 0))     # 2h
        self._emarge(12)                # lundi, aucune heure tapée
        self.assertEqual(self._hours(), Decimal('2'))

    def test_journee_continue_franco_arabe(self):
        self._slot((8, 0), (15, 15))    # 7h15 en continu — pas de matin/après-midi
        self._emarge(12)
        self.assertEqual(self._hours(), Decimal('7.25'))

    def test_cours_du_soir(self):
        self._slot((18, 0), (20, 0))    # 2h le soir — aucune limite d'horaire
        self._emarge(12)
        self.assertEqual(self._hours(), Decimal('2'))

    def test_heures_tapees_prioritaires_sur_le_creneau(self):
        self._slot((8, 0), (10, 0))     # 2h prévues
        self._emarge(12, hours='1.5')   # partiel : seulement 1h30
        self.assertEqual(self._hours(), Decimal('1.5'))

    def test_sans_creneau_repli_sur_duration_hours(self):
        self._emarge(12)                # aucun créneau ce lundi → filet 2h
        self.assertEqual(self._hours(), Decimal('2'))

    def test_plus_de_x2_journee(self):
        # Ancien hack : session='full' × 2. Désormais = somme des créneaux (2h), pas 4h.
        self._slot((8, 0), (10, 0))
        self._emarge(12, session='full')
        self.assertEqual(self._hours(), Decimal('2'))
