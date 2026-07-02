"""Tests de la boucle de retour — Phase 5 (analytics, données synthétiques).

Lancement : python manage.py test apps.lessons.tests_analytics
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.lessons.models import Lesson, LessonContentVersion, LessonDeployment, LessonStatus
from apps.lessons import analytics

User = get_user_model()


class AnalyticsTest(TestCase):

    def setUp(self):
        from apps.schools.models import School, SchoolClass
        from apps.students.models import Student
        from apps.student_learning.models import ExamAttempt, QuizAttempt

        self.teacher = User.objects.create_user(
            phone_number='70009005', full_name='Prof', password='x')
        self.school = School.objects.create(name='École', city='Bamako')
        self.sclass = SchoolClass.objects.create(
            school=self.school, name='6A', level='fondamental_2', annual_fee=0)

        def mk_student(name):
            return Student.objects.create(
                school=self.school, school_class=self.sclass, full_name=name, tuition_fee=0)
        self.s1, self.s2, self.s3, self.s4 = (mk_student(n) for n in ('S1', 'S2', 'S3', 'S4'))

        self.lesson = Lesson.objects.create(
            teacher=self.teacher, school=self.school, title='L', subject='Géo',
            level='fondamental_2', format_version=2, status=LessonStatus.READY)
        self.v1 = LessonContentVersion.objects.create(lesson=self.lesson, version=1)
        self.lesson.active_content_version = self.v1
        self.lesson.save(update_fields=['active_content_version'])
        LessonDeployment.objects.create(
            lesson=self.lesson, school=self.school, school_class=self.sclass,
            deployed_by=self.teacher, is_active=True)

        # s1 : 2 tentatives (0.4 puis 0.8 = meilleure), réussie.
        for score, passed in ((0.4, False), (0.8, True)):
            ExamAttempt.objects.create(
                student=self.s1, lesson=self.lesson, content_version=self.v1,
                pass_mark=0.6, score=score, passed=passed,
                answers=[{'quiz_id': 'e1', 'concept_id': 'c1', 'is_correct': True},
                         {'quiz_id': 'e2', 'concept_id': 'c2', 'is_correct': (score > 0.6)}])
        # s2 : échec 0.4.
        ExamAttempt.objects.create(
            student=self.s2, lesson=self.lesson, content_version=self.v1,
            pass_mark=0.6, score=0.4, passed=False,
            answers=[{'quiz_id': 'e1', 'concept_id': 'c1', 'is_correct': False},
                     {'quiz_id': 'e2', 'concept_id': 'c2', 'is_correct': False}])
        # s4 : pas d'examen, quiz 2/4.
        for ok in (True, True, False, False):
            QuizAttempt.objects.create(
                student=self.s4, lesson=self.lesson, quiz_id='q', question_type='mcq_single',
                student_answer={'i': 0}, is_correct=ok, content_version=self.v1)
        # s3 : rien.

    def test_lesson_results_summary(self):
        r = analytics.lesson_results(self.lesson)
        self.assertEqual(r['cohort'], 4)
        self.assertEqual(r['started'], 3)          # s1, s2, s4
        self.assertEqual(r['not_started'], 1)      # s3
        self.assertEqual(r['passed'], 1)           # s1
        self.assertAlmostEqual(r['avg_exam_score'], 0.6)   # (0.8 + 0.4) / 2

    def test_student_mastery(self):
        self.assertEqual(analytics.student_lesson_mastery(self.s1, self.lesson), 0.8)  # meilleur examen
        self.assertEqual(analytics.student_lesson_mastery(self.s4, self.lesson), 0.5)  # quiz 2/4
        self.assertIsNone(analytics.student_lesson_mastery(self.s3, self.lesson))      # rien

    def test_concept_breakdown(self):
        by_c = {c['concept_id']: c for c in analytics.concept_breakdown(self.lesson)}
        # meilleures tentatives : s1(c1 ok, c2 ok) + s2(c1 faux, c2 faux)
        self.assertEqual(by_c['c1']['rate'], 0.5)   # 1/2
        self.assertEqual(by_c['c2']['rate'], 0.5)   # 1/2 (s1 c2 correct car score 0.8 > 0.6)

    def test_strugglers_signal(self):
        strg = {x['student'].pk for x in analytics.strugglers(self.lesson, threshold=0.5)}
        self.assertIn(self.s2.pk, strg)        # 0.4 < 0.5
        self.assertNotIn(self.s1.pk, strg)     # 0.8
        self.assertNotIn(self.s4.pk, strg)     # 0.5 n'est pas < 0.5
        self.assertNotIn(self.s3.pk, strg)     # pas commencé → non jugé
