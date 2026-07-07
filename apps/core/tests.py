"""
Tests d'isolation multi-écoles (multi-tenant) — tous les rôles.

Garantit qu'aucun rôle ne peut accéder aux données d'une école / d'un élève
auxquels il n'a pas droit. C'est la frontière de sécurité la plus sensible.

Lancer : venv/bin/python manage.py test apps.core
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole, Membership, StaffPermission
from apps.schools.models import School, SchoolClass, SchoolGroup, Subject, ClassSubject
from apps.students.models import Student, StudentGuardian


class MultiTenantIsolationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # ── Deux écoles totalement indépendantes ──
        cls.school_a = School.objects.create(
            name='École A', short_name='A', city='Bamako', school_type='primary',
        )
        cls.school_b = School.objects.create(
            name='École B', short_name='B', city='Bamako', school_type='primary',
        )

        # Directeur par école (via Membership = source de l'isolation).
        cls.dir_a = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir A',
        )
        cls.dir_b = User.objects.create_user(
            phone_number='70000002', password='pw', role=UserRole.DIRECTOR, full_name='Dir B',
        )
        Membership.objects.create(user=cls.dir_a, school=cls.school_a, role=UserRole.DIRECTOR, is_default=True)
        Membership.objects.create(user=cls.dir_b, school=cls.school_b, role=UserRole.DIRECTOR, is_default=True)

        # Classes + élèves : A (classe du prof), A2 (autre classe de A), B (autre école).
        cls.class_a = SchoolClass.objects.create(
            school=cls.school_a, name='1A', level='fondamental_1', annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.class_a2 = SchoolClass.objects.create(
            school=cls.school_a, name='2A', level='fondamental_1', annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.class_b = SchoolClass.objects.create(
            school=cls.school_b, name='1B', level='fondamental_1', annual_fee=Decimal('100000'), max_capacity=40,
        )
        # Noms volontairement distincts (pour tester les fuites de contenu).
        cls.student_a = Student.objects.create(
            school=cls.school_a, school_class=cls.class_a, full_name='Awa Traore', tuition_fee=Decimal('100000'),
        )
        cls.student_a2 = Student.objects.create(
            school=cls.school_a, school_class=cls.class_a2, full_name='Coumba Diallo', tuition_fee=Decimal('100000'),
        )
        cls.student_b = Student.objects.create(
            school=cls.school_b, school_class=cls.class_b, full_name='Bintou Sanogo', tuition_fee=Decimal('100000'),
        )

        # PARENT lié uniquement à l'élève A.
        cls.parent = User.objects.create_user(
            phone_number='72000001', password='pw', role=UserRole.PARENT, full_name='Parent A',
        )
        StudentGuardian.objects.create(guardian=cls.parent, student=cls.student_a, relationship='père')

        # ENSEIGNANT de l'école A, assigné à la classe A uniquement (pas A2).
        cls.teacher = User.objects.create_user(
            phone_number='73000001', password='pw', role=UserRole.TEACHER, full_name='Prof A',
        )
        Membership.objects.create(user=cls.teacher, school=cls.school_a, role=UserRole.TEACHER, is_default=True)
        subject = Subject.objects.create(school=cls.school_a, name='Maths')
        ClassSubject.objects.create(school_class=cls.class_a, subject=subject, teacher=cls.teacher, is_active=True)

        # PROMOTEUR propriétaire d'un groupe contenant SEULEMENT l'école A.
        cls.promoter = User.objects.create_user(
            phone_number='76000001', password='pw', role=UserRole.PROMOTER, full_name='Promo',
        )
        group = SchoolGroup.objects.create(name='Groupe Promo', owner=cls.promoter)
        cls.school_a.group = group
        cls.school_a.save(update_fields=['group'])

        # STAFF de l'école A SANS permission comptabilité.
        cls.staff = User.objects.create_user(
            phone_number='74000001', password='pw', role=UserRole.STAFF, full_name='Staff A',
        )
        staff_m = Membership.objects.create(user=cls.staff, school=cls.school_a, role=UserRole.STAFF, is_default=True)
        StaffPermission.objects.create(user=cls.staff, membership=staff_m, can_manage_accounting=False)

    # ── DIRECTEUR ──────────────────────────────────────────────
    def test_directeur_voit_son_propre_eleve(self):
        self.client.force_login(self.dir_a)
        r = self.client.get(reverse('students:detail', args=[self.student_a.id]))
        self.assertEqual(r.status_code, 200)

    def test_directeur_ne_voit_pas_eleve_autre_ecole(self):
        self.client.force_login(self.dir_a)
        r = self.client.get(reverse('students:detail', args=[self.student_b.id]))
        self.assertEqual(r.status_code, 404)

    def test_switch_school_sans_membership_interdit(self):
        self.client.force_login(self.dir_a)
        r = self.client.post(reverse('accounts:switch-school', args=[self.school_b.id]))
        self.assertEqual(r.status_code, 403)

    def test_session_forgee_est_ignoree(self):
        self.client.force_login(self.dir_a)
        session = self.client.session
        session['active_school_id'] = self.school_b.id
        session.save()
        self.assertEqual(self.client.get(reverse('students:detail', args=[self.student_b.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('students:detail', args=[self.student_a.id])).status_code, 200)

    # ── PARENT ─────────────────────────────────────────────────
    def test_parent_ne_voit_que_ses_enfants(self):
        from apps.parent.children import parent_students
        kids = parent_students(self.parent)
        self.assertIn(self.student_a, kids)       # son enfant
        self.assertNotIn(self.student_b, kids)    # jamais l'enfant d'un autre
        self.assertNotIn(self.student_a2, kids)   # ni un autre élève non lié

    # ── ENSEIGNANT ─────────────────────────────────────────────
    def test_enseignant_ne_voit_pas_eleve_hors_ses_classes(self):
        self.client.force_login(self.teacher)
        # élève d'une classe qu'il n'enseigne pas (même école) → 403
        r = self.client.get(reverse('teacher:student-detail', args=[self.student_a2.id]))
        self.assertEqual(r.status_code, 403)
        # son propre élève (classe qu'il enseigne) → 200
        r_ok = self.client.get(reverse('teacher:student-detail', args=[self.student_a.id]))
        self.assertEqual(r_ok.status_code, 200)

    # ── PROMOTEUR ──────────────────────────────────────────────
    def test_promoteur_ne_voit_que_ses_ecoles(self):
        self.client.force_login(self.promoter)
        r_a = self.client.get(reverse('promoter:school-detail', args=[self.school_a.id]))
        self.assertEqual(r_a.status_code, 200)                 # école de son groupe
        r_b = self.client.get(reverse('promoter:school-detail', args=[self.school_b.id]))
        self.assertEqual(r_b.status_code, 404)                 # école hors de son groupe

    # ── STAFF à permissions restreintes ────────────────────────
    def test_staff_sans_permission_compta_bloque(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse('accounting:dashboard'))
        self.assertEqual(r.status_code, 403)

    # ── Isolation en PROFONDEUR (mutations, argent, vue forgée) ─
    def test_directeur_ne_peut_pas_editer_eleve_autre_ecole(self):
        # Charger le formulaire d'édition d'un élève de l'autre école → 404 (write isolé).
        self.client.force_login(self.dir_a)
        r = self.client.get(reverse('students:update', args=[self.student_b.id]))
        self.assertEqual(r.status_code, 404)
        # Son propre élève reste éditable.
        self.assertNotEqual(
            self.client.get(reverse('students:update', args=[self.student_a.id])).status_code, 404
        )

    def test_argent_isole_entre_ecoles(self):
        # Le panneau d'encaissement (l'ARGENT) d'un élève de l'autre école → 404.
        self.client.force_login(self.dir_a)
        r = self.client.get(reverse('finance:collect-panel', args=[self.student_b.id]))
        self.assertEqual(r.status_code, 404)
        r_ok = self.client.get(reverse('finance:collect-panel', args=[self.student_a.id]))
        self.assertEqual(r_ok.status_code, 200)

    def test_parent_child_forge_ne_fuite_pas(self):
        # Forcer ?child=<élève non lié> ne doit JAMAIS afficher ses données.
        self.client.force_login(self.parent)
        r = self.client.get(reverse('parent:scolarite') + f'?child={self.student_b.id}')
        self.assertNotContains(r, 'Bintou')   # jamais l'enfant non lié (statut 200 vérifié aussi)
        self.assertContains(r, 'Awa')         # bien son propre enfant
