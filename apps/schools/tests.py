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
