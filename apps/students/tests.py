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
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus, StudentGuardian
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


class ResponsablesTests(TestCase):
    """Couche « responsable » (StudentGuardian) : info seule vs accès portail, contact
    principal, non-régression du portail parent. Voir apps/students/models.py + views.py."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École R', short_name='ER', city='Bamako', school_type='primary',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )

    def _student(self, first='A', last='X'):
        return Student.objects.create(
            school=self.school, school_class=self.klass,
            first_name=first, last_name=last, tuition_fee=Decimal('0'),
        )

    # ── Modèle ─────────────────────────────────────────────────
    def test_responsable_info_seule(self):
        s = self._student()
        g = StudentGuardian.objects.create(
            student=s, full_name='Traoré Sékou', phone='76000001',
            relationship='father', is_primary=True,
        )
        self.assertFalse(g.has_portal_access)          # pas de compte
        self.assertEqual(g.display_name, 'Traoré Sékou')
        self.assertEqual(g.display_phone, '76000001')

    def test_responsable_portal_fallback_sur_compte(self):
        from apps.accounts.models import User, UserRole
        s = self._student()
        u = User.objects.create_user(
            phone_number='76000002', password='x', full_name='Diallo Aminata',
            role=UserRole.PARENT,
        )
        g = StudentGuardian.objects.create(student=s, guardian=u)  # sans full_name/phone
        self.assertTrue(g.has_portal_access)
        self.assertEqual(g.display_name, 'Diallo Aminata')   # repli sur le compte
        self.assertEqual(g.display_phone, '76000002')

    def test_has_parent_linked_selon_responsables(self):
        s = self._student()
        self.assertFalse(s.has_parent_linked())
        StudentGuardian.objects.create(student=s, full_name='X', phone='7', is_primary=True)
        self.assertTrue(s.has_parent_linked())

    def test_filtre_sans_responsable(self):
        s_none = self._student(last='Sans')
        s_with = self._student(last='Avec')
        StudentGuardian.objects.create(student=s_with, full_name='R', phone='7', is_primary=True)
        without = Student.objects.filter(school=self.school, guardians__isnull=True)
        self.assertIn(s_none, without)
        self.assertNotIn(s_with, without)

    # ── Non-régression portail parent ──────────────────────────
    def test_portail_parent_exclut_info_seule(self):
        from apps.accounts.models import User, UserRole
        from apps.parent.children import parent_students
        s = self._student()
        u = User.objects.create_user(
            phone_number='76000003', password='x', full_name='Papa', role=UserRole.PARENT,
        )
        # Responsable info seule (aucun compte) → le parent u n'a AUCUN enfant lié.
        StudentGuardian.objects.create(student=s, full_name='Info', phone='7', is_primary=True)
        self.assertEqual(parent_students(u), [])
        # Accès portail accordé → l'enfant apparaît.
        StudentGuardian.objects.create(student=s, guardian=u)
        self.assertIn(s, parent_students(u))

    # ── Helper de création (inscription / fiche) ───────────────
    def test_create_from_post_info(self):
        from django.test import RequestFactory
        from apps.students.views import _create_responsable_from_post
        s = self._student()
        req = RequestFactory().post('/', {
            'responsable_name': 'Traoré Sékou', 'responsable_phone': '76000010',
            'responsable_relationship': 'father',
        })
        g, creds = _create_responsable_from_post(req, s, is_primary=True)
        self.assertIsNotNone(g)
        self.assertFalse(g.has_portal_access)
        self.assertIsNone(creds)                       # info seule → pas de compte → pas d'identifiants
        self.assertEqual(g.full_name, 'Traoré Sékou')
        self.assertTrue(g.is_primary)

    def test_create_from_post_avec_portail(self):
        from django.test import RequestFactory
        from apps.accounts.models import UserRole
        from apps.students.views import _create_responsable_from_post
        s = self._student()
        req = RequestFactory().post('/', {
            'responsable_name': 'Diallo Aminata', 'responsable_phone': '76000011',
            'responsable_relationship': 'mother', 'responsable_portal': 'on',
        })
        g, creds = _create_responsable_from_post(req, s, is_primary=True)
        self.assertTrue(g.has_portal_access)
        self.assertEqual(g.guardian.phone_number, '76000011')
        self.assertEqual(g.guardian.role, UserRole.PARENT)
        # Compte créé → identifiants à afficher UNE fois (sinon mot de passe perdu).
        self.assertIsNotNone(creds)
        self.assertEqual(creds['phone'], '76000011')
        self.assertTrue(creds['temp_pwd'])
        self.assertEqual(creds['children_display'], s.full_name)   # 1 enfant → son nom

    def test_create_from_post_vide(self):
        from django.test import RequestFactory
        from apps.students.views import _create_responsable_from_post
        s = self._student()
        req = RequestFactory().post('/', {})
        self.assertEqual(_create_responsable_from_post(req, s), (None, None))

    def test_format_children_display(self):
        from apps.students.views import _format_children_display
        self.assertEqual(_format_children_display([]), '')
        self.assertEqual(_format_children_display(['Awa']), 'Awa')
        self.assertEqual(_format_children_display(['Awa', 'Moussa']), 'Awa et Moussa')
        self.assertEqual(_format_children_display(['Awa', 'Moussa', 'Fatou']), 'Awa, Moussa et Fatou')
        self.assertEqual(_format_children_display(['A', 'B', 'C', 'D']), 'vos enfants')
        self.assertEqual(_format_children_display(['Awa', 'Awa']), 'Awa')   # dédoublonné

    def test_carte_eleve_nom_authentifie(self):
        # Le nom affiché sur la carte DOIT être accepté par le login (un seul token).
        from apps.students.views import student_login_name
        from apps.core.student_auth import authenticate_student
        s = self._student()   # full_name « Prénom Nom », last_name éventuellement vide
        shown = student_login_name(s)
        self.assertNotIn(' ', shown)                        # un seul mot, jamais « Prénom Nom »
        self.assertIsNotNone(authenticate_student(s.access_code, shown))   # login OK
        # Le nom complet (piège de l'ancienne carte) doit, lui, être refusé.
        if ' ' in s.full_name:
            self.assertIsNone(authenticate_student(s.access_code, s.full_name))

    def test_temp_password_sans_caractere_ambigu(self):
        from apps.accounts.team_forms import generate_temp_password
        ambigu = set('IO01l')
        for _ in range(200):
            p = generate_temp_password()
            self.assertFalse(ambigu & set(p), f'caractère ambigu dans {p}')
            self.assertTrue(p.isupper() or p.isdigit())   # une seule casse (majuscule)

    def test_inscription_view_cree_responsable(self):
        # Flux complet : POST d'inscription avec responsable → élève + responsable principal.
        from django.urls import reverse
        from apps.accounts.models import User, UserRole, Membership
        SchoolYear.objects.create(
            school=self.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        director = User.objects.create_user(
            phone_number='70000099', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        Membership.objects.create(
            user=director, school=self.school, role=UserRole.DIRECTOR, is_default=True,
        )
        self.client.force_login(director)
        session = self.client.session
        session['active_school_id'] = self.school.id
        session.save()
        self.client.post(reverse('students:create'), {
            'school_class': self.klass.id, 'last_name': 'Keita', 'first_name': 'Modibo',
            'gender': 'F', 'date_of_birth': '2015-05-10',
            'responsable_name': 'Keita Awa', 'responsable_phone': '76001234',
            'responsable_relationship': 'mother',
        }, HTTP_HX_REQUEST='true')
        student = Student.objects.get(school=self.school, last_name='Keita', first_name='Modibo')
        g = student.guardians.get()
        self.assertEqual(g.full_name, 'Keita Awa')
        self.assertTrue(g.is_primary)
        self.assertFalse(g.has_portal_access)
        self.assertTrue(student.matricule)      # matricule auto attribué


class StudentLifecycleTests(TestCase):
    """Archivage / réactivation : transition de l'inscription (jamais de doublon),
    aller-retour, diplômé terminal, idempotence, et le withdraw qui ne plante plus.
    Voir Student.archive / reactivate."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École L', short_name='EL', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )

    def _enrolled(self, first='A', last='X'):
        s = Student.objects.create(
            school=self.school, school_class=self.klass,
            first_name=first, last_name=last, tuition_fee=Decimal('0'),
        )
        ensure_active_enrollment(s)   # inscription ACTIVE (comme à la vraie inscription)
        return s

    def test_archive_transition_sans_doublon(self):
        s = self._enrolled()
        s.archive(EnrollmentStatus.WITHDRAWN)
        self.assertFalse(s.is_active)
        enrs = StudentEnrollment.objects.filter(student=s)
        self.assertEqual(enrs.count(), 1)                        # PAS de doublon
        self.assertEqual(enrs.first().status, EnrollmentStatus.WITHDRAWN)
        self.assertIsNotNone(enrs.first().ended_at)

    def test_archive_ne_plante_pas(self):
        # Bug d'origine : archiver un élève normalement inscrit levait IntegrityError.
        s = self._enrolled()
        try:
            s.archive(EnrollmentStatus.TRANSFERRED)
        except Exception as e:                       # noqa: BLE001
            self.fail(f'archive() a planté : {e}')

    def test_reactivate_aller_retour(self):
        s = self._enrolled()
        s.archive(EnrollmentStatus.WITHDRAWN)
        self.assertTrue(s.reactivate())
        self.assertTrue(s.is_active)
        enr = StudentEnrollment.objects.get(student=s)
        self.assertEqual(enr.status, EnrollmentStatus.ACTIVE)    # retour à ACTIVE
        self.assertIsNone(enr.ended_at)

    def test_reactivate_diplome_bloque(self):
        s = self._enrolled()
        s.archive(EnrollmentStatus.GRADUATED)
        self.assertFalse(s.reactivate())                        # diplômé = terminal
        self.assertFalse(s.is_active)                           # reste archivé

    def test_idempotence(self):
        s = self._enrolled()
        s.archive(EnrollmentStatus.WITHDRAWN)
        s.archive(EnrollmentStatus.WITHDRAWN)                   # 2e fois → pas d'erreur
        self.assertEqual(StudentEnrollment.objects.filter(student=s).count(), 1)

    def test_withdraw_view_ne_plante_plus(self):
        # Intégration : le bouton « Retirer » (500 avant le fix) fonctionne.
        from django.urls import reverse
        from apps.accounts.models import User, UserRole, Membership
        director = User.objects.create_user(
            phone_number='70000070', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        Membership.objects.create(
            user=director, school=self.school, role=UserRole.DIRECTOR, is_default=True,
        )
        s = self._enrolled()
        self.client.force_login(director)
        session = self.client.session
        session['active_school_id'] = self.school.id
        session.save()
        resp = self.client.post(reverse('students:withdraw', args=[s.id]), {'status': 'withdrawn'})
        self.assertIn(resp.status_code, (200, 204))             # plus de 500
        s.refresh_from_db()
        self.assertFalse(s.is_active)
