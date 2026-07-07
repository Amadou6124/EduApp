"""
Tests d'isolation multi-écoles (multi-tenant).

Garantit qu'un directeur de l'école A ne peut JAMAIS accéder aux données de
l'école B — ni par un id direct, ni en forçant la session, ni via switch-school.
C'est la frontière de sécurité la plus sensible de l'app.

Lancer : venv/bin/python manage.py test apps.core
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole, Membership
from apps.schools.models import School, SchoolClass
from apps.students.models import Student


class MultiTenantIsolationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # Deux écoles totalement indépendantes.
        cls.school_a = School.objects.create(
            name='École A', short_name='A', city='Bamako', school_type='primary',
        )
        cls.school_b = School.objects.create(
            name='École B', short_name='B', city='Bamako', school_type='primary',
        )

        # Un directeur par école, rattaché via Membership (source de l'isolation).
        cls.dir_a = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir A',
        )
        cls.dir_b = User.objects.create_user(
            phone_number='70000002', password='pw', role=UserRole.DIRECTOR, full_name='Dir B',
        )
        Membership.objects.create(user=cls.dir_a, school=cls.school_a, role=UserRole.DIRECTOR, is_default=True)
        Membership.objects.create(user=cls.dir_b, school=cls.school_b, role=UserRole.DIRECTOR, is_default=True)

        # Une classe + un élève dans chaque école.
        cls.class_a = SchoolClass.objects.create(
            school=cls.school_a, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.class_b = SchoolClass.objects.create(
            school=cls.school_b, name='1B', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.student_a = Student.objects.create(
            school=cls.school_a, school_class=cls.class_a, full_name='Élève A',
            tuition_fee=Decimal('100000'),
        )
        cls.student_b = Student.objects.create(
            school=cls.school_b, school_class=cls.class_b, full_name='Élève B',
            tuition_fee=Decimal('100000'),
        )

    def setUp(self):
        # Connecté en directeur de l'école A pour tous les tests.
        self.client.force_login(self.dir_a)

    def test_directeur_voit_son_propre_eleve(self):
        r = self.client.get(reverse('students:detail', args=[self.student_a.id]))
        self.assertEqual(r.status_code, 200)

    def test_directeur_ne_voit_pas_eleve_autre_ecole(self):
        # L'élève B (école B) doit être introuvable pour le directeur A → 404, jamais 200.
        r = self.client.get(reverse('students:detail', args=[self.student_b.id]))
        self.assertEqual(r.status_code, 404)

    def test_switch_school_sans_membership_interdit(self):
        # Basculer sur l'école B (aucun membership) doit être refusé → 403.
        # (La vue exige un POST ; un GET renverrait 405.)
        r = self.client.post(reverse('accounts:switch-school', args=[self.school_b.id]))
        self.assertEqual(r.status_code, 403)

    def test_session_forgee_est_ignoree(self):
        # Forcer active_school_id sur l'école B en session ne doit rien débloquer :
        # get_school valide contre les Memberships et retombe sur l'école A.
        session = self.client.session
        session['active_school_id'] = self.school_b.id
        session.save()

        # L'élève B reste inaccessible…
        r_b = self.client.get(reverse('students:detail', args=[self.student_b.id]))
        self.assertEqual(r_b.status_code, 404)
        # …et l'élève A reste bien accessible.
        r_a = self.client.get(reverse('students:detail', args=[self.student_a.id]))
        self.assertEqual(r_a.status_code, 200)
