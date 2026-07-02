"""Tests de la vue Résultats — Phase 9 (boucle de retour, front).

Prouve le chemin RICHE (concepts nommés + question qui coince + élèves à aider)
avec données synthétiques, plus les états vides honnêtes et l'isolation par prof.
Le rendu visuel est confirmé en preview ; ici on cible le contenu HTML.

Lancement : python manage.py test apps.lessons.tests_results_view
"""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.lessons.models import (
    Lesson, LessonContentVersion, LessonDeployment, LessonStatus)
from apps.schools.models import School, SchoolClass
from apps.students.models import Student
from apps.student_learning.models import ExamAttempt

User = get_user_model()

CONCEPTS = [
    {'id': 'c1', 'name': 'La phrase déclarative', 'quiz': []},
    {'id': 'c2', 'name': 'La phrase impérative', 'quiz': []},
]
EXAM = {'pass_mark': 0.6, 'questions': [
    {'id': 'e1', 'concept_id': 'c1', 'instruction': 'Question un déclarative'},
    {'id': 'e2', 'concept_id': 'c2', 'instruction': 'Question deux impérative'},
]}


class ResultsViewTest(TestCase):

    def setUp(self):
        self.school = School.objects.create(name='École', city='Bamako')
        self.teacher = User.objects.create_user(
            phone_number='70005000', full_name='Prof', password='x')
        self.teacher.is_superuser = True
        self.teacher.school = self.school
        self.teacher.save()
        self.client.force_login(self.teacher)
        self.sclass = SchoolClass.objects.create(
            school=self.school, name='6A', level='fondamental_2', annual_fee=0)

        def mk(name):
            return Student.objects.create(
                school=self.school, school_class=self.sclass, full_name=name, tuition_fee=0)
        self.s1, self.s2, self.s3, self.s4 = (mk(n) for n in
                                              ('Awa Diallo', 'Bakary Coulibaly', 'Cheick Sanogo', 'Diana Touré'))

        self.lesson = Lesson.objects.create(
            teacher=self.teacher, school=self.school, title='Les types de phrases',
            subject='Français', level='fondamental_1', format_version=2, status=LessonStatus.READY)
        self.cv = LessonContentVersion.objects.create(
            lesson=self.lesson, version=1, concepts_data=CONCEPTS, exam_data=EXAM)
        self.lesson.active_content_version = self.cv
        self.lesson.save(update_fields=['active_content_version'])

    def _deploy(self):
        LessonDeployment.objects.create(
            lesson=self.lesson, school=self.school, school_class=self.sclass,
            deployed_by=self.teacher, is_active=True)

    def _exam(self, student, score, passed, e1_ok, e2_ok):
        ExamAttempt.objects.create(
            student=student, lesson=self.lesson, content_version=self.cv,
            pass_mark=0.6, score=score, passed=passed,
            answers=[{'quiz_id': 'e1', 'concept_id': 'c1', 'is_correct': e1_ok},
                     {'quiz_id': 'e2', 'concept_id': 'c2', 'is_correct': e2_ok}])

    def _get(self):
        return self.client.get(reverse('lessons:results', args=[self.lesson.id]))

    # ── chemin riche ─────────────────────────────────────────────────────────
    def test_rich_results_render(self):
        self._deploy()
        self._exam(self.s1, 0.8, True,  True, True)    # tout bon
        self._exam(self.s2, 0.4, False, True, False)   # rate l'impératif
        self._exam(self.s3, 0.4, False, True, False)   # rate l'impératif
        # s4 : pas d'activité

        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        # concepts nommés + taux (c1 100%, c2 33%)
        self.assertContains(resp, 'La phrase déclarative')
        self.assertContains(resp, 'La phrase impérative')
        self.assertContains(resp, '100%')
        self.assertContains(resp, '33%')
        self.assertContains(resp, 'à reprendre')            # c2 sous 40 %
        # la question qui coince (énoncé + taux d'échec 2/3 = 67 %)
        self.assertContains(resp, 'Question deux impérative')
        self.assertContains(resp, '67% ratée')
        # élèves à aider (s2, s3 sous 50 %)
        self.assertContains(resp, 'Bakary Coulibaly')
        self.assertContains(resp, 'Cheick Sanogo')
        # participation
        ctx = resp.context
        self.assertEqual(ctx['summary']['cohort'], 4)
        self.assertEqual(ctx['summary']['started'], 3)
        self.assertEqual(ctx['summary']['passed'], 1)

    def test_concept_sorted_best_first(self):
        self._deploy()
        self._exam(self.s1, 0.8, True, True, True)
        self._exam(self.s2, 0.4, False, True, False)
        names = [c['name'] for c in self._get().context['concepts']]
        self.assertEqual(names[0], 'La phrase déclarative')   # meilleur taux d'abord

    # ── états vides ──────────────────────────────────────────────────────────
    def test_not_deployed_empty_state(self):
        resp = self._get()
        self.assertContains(resp, 'Pas encore de résultats')

    def test_deployed_no_activity_empty_state(self):
        self._deploy()
        resp = self._get()
        self.assertContains(resp, "Personne n'a encore commencé")

    def test_concept_fallback_without_exam(self):
        self._deploy()
        from apps.student_learning.models import QuizAttempt
        QuizAttempt.objects.create(
            student=self.s1, lesson=self.lesson, quiz_id='q', question_type='mcq_single',
            student_answer={'i': 0}, is_correct=True, content_version=self.cv)
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'après les premiers')     # pas d'examen encore

    # ── sécurité ─────────────────────────────────────────────────────────────
    def test_other_teacher_404(self):
        other = User.objects.create_user(
            phone_number='70006000', full_name='Autre', password='x')
        other.is_superuser = True
        other.school = School.objects.create(name='Autre école', city='Ségou')
        other.save()
        self.client.force_login(other)
        self.assertEqual(self._get().status_code, 404)
