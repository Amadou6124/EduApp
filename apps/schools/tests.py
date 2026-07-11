"""
Tests des calculs Notes → Bulletins (les notes des élèves — zéro erreur tolérée).

Couvre la formule malienne de moyenne (devoir + composition×2)/3, la moyenne
générale pondérée par coefficients, et le rang de classe avec ex æquo (classement
« compétition » : 1, 2, 2, 4).

Lancer : venv/bin/python manage.py test apps.schools
"""
from decimal import Decimal
from datetime import date
from types import SimpleNamespace

from django.test import TestCase

from apps.accounts.models import User, UserRole
from apps.schools.models import School, SchoolYear, SchoolClass, Period, Bulletin
from apps.students.models import Student
from apps.schools.services.bulletin_calculator import BulletinCalculator


def _note(value, position):
    """Faux Note minimal (le calculateur ne lit que value/position/is_cancelled)."""
    return SimpleNamespace(value=Decimal(str(value)), position=position, is_cancelled=False)


class BulletinCalcPureTests(TestCase):
    """Calculs purs (sans base de données)."""

    def setUp(self):
        self.calc = BulletinCalculator()

    def test_moyenne_matiere_formule_malienne(self):
        # (note de classe + composition×2) / 3 = (12 + 15×2)/3 = 42/3 = 14.
        moy = self.calc.calculate_subject_average(
            [_note(12, 1), _note(15, 2)], max_grade=Decimal('20'),
        )
        self.assertEqual(moy, Decimal('14'))

    def test_moyenne_matiere_incomplete_renvoie_none(self):
        # Composition manquante → pas de moyenne (None), jamais un chiffre faux.
        moy = self.calc.calculate_subject_average([_note(12, 1)], max_grade=Decimal('20'))
        self.assertIsNone(moy)

    def test_note_ponderee(self):
        self.assertEqual(self.calc.calculate_weighted_grade(Decimal('14'), Decimal('2')), Decimal('28'))

    def test_moyenne_generale_ponderee(self):
        # (14×2 + 14×1) / (2+1) = 42/3 = 14.
        moy = self.calc.calculate_general_average([
            {'weighted_grade': Decimal('28'), 'coefficient': Decimal('2')},
            {'weighted_grade': Decimal('14'), 'coefficient': Decimal('1')},
        ])
        self.assertEqual(moy, Decimal('14'))

    def test_moyenne_generale_ignore_matiere_sans_note(self):
        # Une matière sans note (weighted None) ne doit pas fausser la moyenne.
        moy = self.calc.calculate_general_average([
            {'weighted_grade': Decimal('30'), 'coefficient': Decimal('2')},
            {'weighted_grade': None, 'coefficient': Decimal('5')},
        ])
        self.assertEqual(moy, Decimal('15'))   # 30/2, la matière sans note ignorée


class BulletinRankTests(TestCase):
    """Rang de classe (avec ex æquo) — nécessite des bulletins en base."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.director = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.period = Period.objects.create(school_year=cls.year, name='Trimestre 1', order=1)
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        # 4 élèves avec des moyennes : 16, 15, 15 (ex æquo), 12.
        cls.students, avgs = [], [Decimal('16'), Decimal('15'), Decimal('15'), Decimal('12')]
        for i, avg in enumerate(avgs):
            s = Student.objects.create(
                school=cls.school, school_class=cls.klass,
                full_name=f'Élève {i}', tuition_fee=Decimal('100000'),
            )
            cls.students.append(s)
            Bulletin.objects.create(
                student=s, period=cls.period, school_class=cls.klass,
                general_average=avg, class_size=4, generated_by=cls.director,
            )

    def test_rang_ex_aequo_classement_competition(self):
        calc = BulletinCalculator()
        ranks = calc.calculate_ranks(self.period, self.klass)
        s0, s1, s2, s3 = self.students
        self.assertEqual(ranks[s0.id], 1)   # 16 → 1er
        self.assertEqual(ranks[s1.id], 2)   # 15 → 2e ex æquo
        self.assertEqual(ranks[s2.id], 2)   # 15 → 2e ex æquo
        self.assertEqual(ranks[s3.id], 4)   # 12 → 4e (le rang 3 est sauté)


class SubjectColorTests(TestCase):
    """Couleur auto des matières : distinctes (zéro collision) jusqu'à la taille de la
    palette + abréviation auto. Voir pick_subject_color / auto_subject_abbrev."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École S', short_name='ES', city='Bamako', school_type='primary',
        )

    def test_couleurs_toutes_distinctes(self):
        from apps.schools.models import Subject, _SUBJECT_PALETTE
        names = ['Maths', 'Français', 'Anglais', 'Physique', 'Chimie', 'SVT',
                 'Histoire', 'Géographie', 'EPS', 'Arabe', 'Philosophie', 'Informatique']
        colors = [Subject.objects.create(school=self.school, name=n).color for n in names]
        self.assertEqual(len(colors), len(set(colors)))       # AUCUNE collision
        self.assertTrue(all(c in _SUBJECT_PALETTE for c in colors))

    def test_abreviation_auto_ignore_stopwords(self):
        from apps.schools.models import Subject
        s = Subject.objects.create(school=self.school, name='Sciences de la Vie et de la Terre')
        self.assertEqual(s.short_name, 'SVT')   # acronyme, « de / la / et » ignorés


class CourseSlotTests(TestCase):
    """Emploi du temps : créneaux libres à la minute, conflits refusés, pauses.
    Contrat : le planning est un GUIDE (jamais de lien avec la paie)."""

    @classmethod
    def setUpTestData(cls):
        from apps.schools.models import Subject, ClassSubject
        cls.school = School.objects.create(
            name='École EDT', short_name='ED', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.year2 = SchoolYear.objects.create(
            school=cls.school, name='2026-2027',
            start_date=date(2026, 10, 1), end_date=date(2027, 6, 30), is_active=False,
        )
        cls.k6a = SchoolClass.objects.create(
            school=cls.school, name='6A', level='fondamental_2',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.k5b = SchoolClass.objects.create(
            school=cls.school, name='5B', level='fondamental_2',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.prof = User.objects.create_user(
            phone_number='70000100', password='pw', role=UserRole.TEACHER, full_name='M. Traoré',
        )
        cls.math   = Subject.objects.create(school=cls.school, name='Maths')
        cls.frans  = Subject.objects.create(school=cls.school, name='Français')
        cls.cs_math_6a  = ClassSubject.objects.create(
            school_class=cls.k6a, subject=cls.math, teacher=cls.prof,
        )
        cls.cs_fr_6a    = ClassSubject.objects.create(
            school_class=cls.k6a, subject=cls.frans, teacher=None,   # sans prof
        )
        cls.cs_math_5b  = ClassSubject.objects.create(
            school_class=cls.k5b, subject=cls.math, teacher=cls.prof,
        )

    def _slot(self, cs, day, start, end, year=None, room=''):
        from apps.schools.models import CourseSlot
        from datetime import time
        s = CourseSlot(
            class_subject=cs, school_year=year or self.year, day=day,
            start_time=time(*start), end_time=time(*end), room=room,
        )
        s.full_clean()
        s.save()
        return s

    def test_journee_reelle_a_la_minute(self):
        # L'exemple exact du fondateur : 8h-11h / 11h15-13h15 / 13h30-15h15 (même classe).
        self._slot(self.cs_math_6a, 0, (8, 0), (11, 0))
        self._slot(self.cs_fr_6a,   0, (11, 15), (13, 15))
        self._slot(self.cs_math_6a, 0, (13, 30), (15, 15))
        from apps.schools.models import CourseSlot
        self.assertEqual(CourseSlot.objects.filter(school_year=self.year, day=0).count(), 3)

    def test_durees_differentes_par_creneau(self):
        # Math 2h le lundi ET 1h le jeudi : durée libre par créneau.
        self._slot(self.cs_math_6a, 0, (8, 0), (10, 0))
        self._slot(self.cs_math_6a, 3, (10, 0), (11, 0))

    def test_conflit_classe_refuse(self):
        from django.core.exceptions import ValidationError
        self._slot(self.cs_math_6a, 0, (8, 0), (10, 0))
        with self.assertRaises(ValidationError):
            self._slot(self.cs_fr_6a, 0, (9, 0), (11, 0))    # même classe, chevauche

    def test_conflit_prof_refuse(self):
        from django.core.exceptions import ValidationError
        self._slot(self.cs_math_6a, 1, (8, 0), (10, 0))
        with self.assertRaises(ValidationError):
            self._slot(self.cs_math_5b, 1, (9, 30), (11, 0))  # même prof, autre classe

    def test_chevauchement_partiel_detecte(self):
        # 8h00-9h30 vs 8h45-10h15 → conflit (le cas vicieux).
        from django.core.exceptions import ValidationError
        self._slot(self.cs_math_6a, 2, (8, 0), (9, 30))
        with self.assertRaises(ValidationError):
            self._slot(self.cs_math_5b, 2, (8, 45), (10, 15))

    def test_creneaux_adjacents_ok(self):
        # 9h-10h puis 10h-11h : PAS un conflit (bord à bord).
        self._slot(self.cs_math_6a, 4, (9, 0), (10, 0))
        self._slot(self.cs_math_5b, 4, (10, 0), (11, 0))

    def test_pas_de_faux_conflit_entre_annees(self):
        # Même horaire, années différentes → OK (l'année N+1 repart proprement).
        self._slot(self.cs_math_6a, 0, (8, 0), (10, 0))
        self._slot(self.cs_math_5b, 0, (8, 0), (10, 0), year=self.year2)

    def test_cours_sans_prof_jamais_en_conflit_prof(self):
        # Français 6A n'a pas de prof → aucun conflit prof possible avec lui.
        self._slot(self.cs_fr_6a, 5, (8, 0), (10, 0))
        self._slot(self.cs_math_5b, 5, (8, 0), (10, 0))      # autre classe, prof libre

    def test_conflit_salle_seulement_si_renseignee(self):
        from django.core.exceptions import ValidationError
        self._slot(self.cs_math_6a, 3, (8, 0), (10, 0), room='Salle 1')
        # Sans salle → pas de conflit salle.
        self._slot(self.cs_fr_6a, 3, (10, 0), (12, 0))
        # Même salle, chevauchement → refusé.
        with self.assertRaises(ValidationError):
            self._slot(self.cs_math_5b, 3, (9, 0), (11, 0), room='salle 1')

    def test_fin_avant_debut_refusee(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self._slot(self.cs_math_6a, 0, (10, 0), (8, 0))

    def test_pause_nommee(self):
        from apps.schools.models import SchoolBreak
        from datetime import time
        b = SchoolBreak(school=self.school, label='Récréation',
                        start_time=time(11, 0), end_time=time(11, 15))
        b.full_clean(); b.save()
        # Vendredi seulement (djoumou'a).
        j = SchoolBreak(school=self.school, label='Djoumou\'a', day=4,
                        start_time=time(13, 0), end_time=time(14, 30))
        j.full_clean(); j.save()
        self.assertEqual(self.school.school_breaks.count(), 2)

    def test_dimanche_franco_arabe(self):
        # Une école franco-arabe (repos vendredi) peut placer des cours le dimanche.
        self._slot(self.cs_math_6a, 6, (8, 0), (10, 0))
        # Et les conflits y sont contrôlés comme les autres jours.
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self._slot(self.cs_math_5b, 6, (9, 0), (11, 0))   # même prof, dimanche


class ResolveSubjectTests(TestCase):
    """Création de matière à la volée : anti-doublon par nom normalisé (casse/accents)."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Volée', short_name='EV', city='Bamako', school_type='primary',
        )

    def test_creation_avec_couleur_auto(self):
        from apps.schools.models import resolve_or_create_subject
        s, created = resolve_or_create_subject(self.school, '  Dessin  ')
        self.assertTrue(created)
        self.assertEqual(s.name, 'Dessin')          # nom nettoyé (trim)
        self.assertTrue(s.color)                    # couleur auto posée par save()

    def test_reutilise_insensible_casse(self):
        from apps.schools.models import Subject, resolve_or_create_subject
        orig = Subject.objects.create(school=self.school, name='Maths')
        s, created = resolve_or_create_subject(self.school, 'maths')
        self.assertFalse(created)
        self.assertEqual(s.id, orig.id)             # réutilisée, pas dupliquée

    def test_reutilise_insensible_accents(self):
        from apps.schools.models import Subject, resolve_or_create_subject
        orig = Subject.objects.create(school=self.school, name='Français')
        s, created = resolve_or_create_subject(self.school, 'francais')
        self.assertFalse(created)
        self.assertEqual(s.id, orig.id)

    def test_reactive_matiere_desactivee(self):
        from apps.schools.models import Subject, resolve_or_create_subject
        old = Subject.objects.create(school=self.school, name='Musique', is_active=False)
        s, created = resolve_or_create_subject(self.school, 'Musique')
        self.assertFalse(created)
        self.assertEqual(s.id, old.id)
        self.assertTrue(Subject.objects.get(pk=old.pk).is_active)   # réactivée

    def test_noms_differents_creent_bien(self):
        from apps.schools.models import Subject, resolve_or_create_subject
        Subject.objects.create(school=self.school, name='Math')
        s, created = resolve_or_create_subject(self.school, 'Maths')   # ≠ normalisé
        self.assertTrue(created)                    # « Math » vs « Maths » = 2 matières


class SchoolYearFormValidationTests(TestCase):
    """Régression : créer une année ACTIVE via le formulaire (school non encore
    attachée) ne doit PAS lever un 500 (RelatedObjectDoesNotExist)."""

    def test_form_is_valid_annee_active_sans_ecole_attachee(self):
        from apps.schools.forms import SchoolYearForm
        form = SchoolYearForm(data={
            'name': '2026-2027', 'start_date': '2026-10-01',
            'end_date': '2027-06-30', 'is_active': True,
        })
        # AVANT le fix : is_valid() plantait sur self.school → 500.
        self.assertTrue(form.is_valid(), form.errors)

    def test_clean_modele_sans_ecole_ne_plante_pas(self):
        y = SchoolYear(name='X', is_active=True)   # aucune école
        y.clean()                                   # ne doit rien lever

    def test_deuxieme_annee_active_toujours_refusee(self):
        from django.core.exceptions import ValidationError
        school = School.objects.create(name='É', short_name='E', city='Bamako',
                                       school_type='primary')
        SchoolYear.objects.create(school=school, name='A', is_active=True,
                                  start_date=date(2025, 10, 1), end_date=date(2026, 6, 30))
        y2 = SchoolYear(school=school, name='B', is_active=True,
                        start_date=date(2026, 10, 1), end_date=date(2027, 6, 30))
        with self.assertRaises(ValidationError):
            y2.clean()                              # le vrai contrôle reste actif


class ClassEditTests(TestCase):
    """#4 — édition classe : erreurs visibles (retarget modal) + doublon non 500."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.accounts.models import Membership, UserRole
        U = get_user_model()
        cls.school = School.objects.create(name='É', short_name='E', city='Bamako',
                                           school_type='primary')
        cls.director = U.objects.create_user(
            phone_number='79990001', password='x', full_name='Dir', role=UserRole.DIRECTOR,
            school=cls.school)
        Membership.objects.create(user=cls.director, school=cls.school,
                                  role=UserRole.DIRECTOR, is_default=True)
        cls.c1 = SchoolClass.objects.create(school=cls.school, name='6ème A',
                                            level='fondamental_2', annual_fee=0, max_capacity=40)
        cls.c2 = SchoolClass.objects.create(school=cls.school, name='9ème A',
                                            level='fondamental_1', annual_fee=0, max_capacity=40)

    def setUp(self):
        self.client.force_login(self.director)

    def _post(self, cls, **over):
        data = {'name': cls.name, 'level': cls.level, 'annual_fee': '0', 'max_capacity': '40'}
        data.update(over)
        return self.client.post(f'/classes/{cls.id}/update/', data,
                                HTTP_HX_REQUEST='true', HTTP_HOST='localhost')

    def test_edition_niveau_reussie(self):
        resp = self._post(self.c2, level='fondamental_2')   # corrige la 9ème
        self.assertEqual(resp.status_code, 200)
        self.assertIn('close-edit-modal', resp.headers.get('HX-Trigger', ''))
        self.assertContains(resp, 'hx-swap-oob')            # ligne mise à jour en OOB
        self.c2.refresh_from_db()
        self.assertEqual(self.c2.level, 'fondamental_2')

    def test_renommage_vers_nom_existant_ne_500_pas(self):
        resp = self._post(self.c2, name='6ème A')           # nom déjà pris (actif)
        self.assertEqual(resp.status_code, 200)             # PAS de 500
        self.assertContains(resp, 'porte déjà ce nom')      # erreur VISIBLE dans le modal
        self.assertNotIn('close-edit-modal', resp.headers.get('HX-Trigger', ''))
        self.c2.refresh_from_db()
        self.assertEqual(self.c2.name, '9ème A')            # inchangé

    def test_form_invalide_reaffiche_le_modal(self):
        resp = self._post(self.c2, name='')                 # nom vide
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Modifier')               # le modal (avec erreurs) est re-rendu
        self.assertNotIn('close-edit-modal', resp.headers.get('HX-Trigger', ''))


class SchoolBreakMultiDayTests(TestCase):
    """#9 — créer une pause sur plusieurs jours précis (lun+mer) en une fois."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.accounts.models import Membership, UserRole
        U = get_user_model()
        cls.school = School.objects.create(name='É', short_name='E', city='Bamako',
                                           school_type='primary')
        cls.director = U.objects.create_user(
            phone_number='79993001', password='x', full_name='Dir',
            role=UserRole.DIRECTOR, school=cls.school, must_change_password=False)
        Membership.objects.create(user=cls.director, school=cls.school,
                                  role=UserRole.DIRECTOR, is_default=True)
        cls.klass = SchoolClass.objects.create(school=cls.school, name='1A',
                                               level='fondamental_1', annual_fee=0, max_capacity=40)

    def setUp(self):
        self.client.force_login(self.director)
        s = self.client.session
        s['active_school_id'] = self.school.id
        s.save()

    def _post(self, **data):
        base = {'label': 'Récré', 'start_time': '10:00', 'end_time': '10:15'}
        base.update(data)
        return self.client.post(f'/classes/{self.klass.id}/edt/break/save/', base,
                                HTTP_HX_REQUEST='true', HTTP_HOST='localhost')

    def test_plusieurs_jours_creent_plusieurs_pauses(self):
        from apps.schools.models import SchoolBreak
        self._post(day=['0', '2'])                    # lundi + mercredi, pas mardi
        days = sorted(SchoolBreak.objects.filter(school=self.school).values_list('day', flat=True))
        self.assertEqual(days, [0, 2])

    def test_tous_les_jours_une_seule_pause_null(self):
        from apps.schools.models import SchoolBreak
        self._post(all_days='1')
        brks = SchoolBreak.objects.filter(school=self.school)
        self.assertEqual(brks.count(), 1)
        self.assertIsNone(brks.first().day)

    def test_aucun_jour_message_clair(self):
        import json
        resp = self._post()                            # ni all_days ni day
        self.assertEqual(resp.status_code, 422)
        self.assertIn('au moins un jour',
                      json.loads(resp.headers['HX-Trigger'])['showToast']['message'])
