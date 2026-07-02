"""Tests du cycle de vie des leçons — Phase 4 (retrait / archivage / suppression).

Règle prouvée : une leçon utilisée s'ARCHIVE (jamais supprimée), une leçon jamais
utilisée se supprime pour de vrai. Le tampon de validation est posé au publish.

Lancement : python manage.py test apps.lessons.tests_lifecycle
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.lessons.models import (Lesson, LessonContentVersion, LessonContentDraft,
                                 LessonDeployment, LessonStatus)
from apps.lessons import lifecycle, versioning

User = get_user_model()


class LifecycleTest(TestCase):

    def setUp(self):
        from apps.schools.models import School, SchoolClass
        from apps.students.models import Student

        self.teacher = User.objects.create_user(
            phone_number='70009003', full_name='Prof Test', password='x')
        self.school = School.objects.create(name='École Test', city='Bamako')
        self.sclass = SchoolClass.objects.create(
            school=self.school, name='6A', level='fondamental_2', annual_fee=0)
        self.student = Student.objects.create(
            school=self.school, school_class=self.sclass, full_name='Élève', tuition_fee=0)

        self.lesson = Lesson.objects.create(
            teacher=self.teacher, school=self.school, title='Le relief', subject='Géo',
            level='fondamental_2', format_version=2, status=LessonStatus.READY)
        self.v1 = LessonContentVersion.objects.create(
            lesson=self.lesson, version=1, concepts_data=[{'id': 'c1'}])
        self.lesson.active_content_version = self.v1
        self.lesson.save(update_fields=['active_content_version'])
        self.deploy = LessonDeployment.objects.create(
            lesson=self.lesson, school=self.school, school_class=self.sclass,
            deployed_by=self.teacher, is_active=True)

    def _add_activity(self):
        from apps.student_learning.models import QuizAttempt
        return QuizAttempt.objects.create(
            student=self.student, lesson=self.lesson, quiz_id='q1',
            question_type='mcq_single', student_answer={'i': 0}, is_correct=True,
            content_version=self.v1)

    # ── tampon de validation ────────────────────────────────────────────────
    def test_publish_with_validator_stamps(self):
        versioning.edit_draft(self.lesson, guide='Awa')
        v2 = versioning.publish_draft(self.lesson, validated_by=self.teacher)
        self.assertEqual(v2.validated_by_id, self.teacher.id)
        self.assertIsNotNone(v2.validated_at)

    def test_publish_without_validator_no_stamp(self):
        versioning.edit_draft(self.lesson, guide='Awa')
        v2 = versioning.publish_draft(self.lesson)
        self.assertIsNone(v2.validated_by_id)
        self.assertIsNone(v2.validated_at)

    # ── retrait ─────────────────────────────────────────────────────────────
    def test_undeploy_all(self):
        n = lifecycle.undeploy_all(self.lesson)
        self.assertEqual(n, 1)
        self.deploy.refresh_from_db()
        self.assertFalse(self.deploy.is_active)

    # ── activité élève ──────────────────────────────────────────────────────
    def test_has_student_activity(self):
        self.assertFalse(lifecycle.has_student_activity(self.lesson))
        self._add_activity()
        self.assertTrue(lifecycle.has_student_activity(self.lesson))

    # ── archivage ───────────────────────────────────────────────────────────
    def test_archive_keeps_everything(self):
        att = self._add_activity()
        lifecycle.archive_lesson(self.lesson)
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.is_archived)
        self.assertIsNotNone(self.lesson.archived_at)
        self.deploy.refresh_from_db()
        self.assertFalse(self.deploy.is_active)                 # dépubliée
        self.assertTrue(LessonContentVersion.objects.filter(pk=self.v1.pk).exists())
        att.refresh_from_db()                                    # tentative gardée
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())

        lifecycle.unarchive_lesson(self.lesson)
        self.lesson.refresh_from_db()
        self.assertFalse(self.lesson.is_archived)

    # ── suppression ─────────────────────────────────────────────────────────
    def test_delete_unused_lesson_really_deletes(self):
        versioning.open_draft(self.lesson)                       # brouillon présent
        lid, vid = self.lesson.pk, self.v1.pk
        lifecycle.delete_lesson(self.lesson)
        self.assertFalse(Lesson.objects.filter(pk=lid).exists())
        self.assertFalse(LessonContentVersion.objects.filter(pk=vid).exists())
        self.assertFalse(LessonContentDraft.objects.filter(lesson_id=lid).exists())

    def test_delete_used_lesson_raises(self):
        self._add_activity()
        with self.assertRaises(ValueError):
            lifecycle.delete_lesson(self.lesson)
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())   # intacte

    # ── remove_lesson choisit ─────────────────────────────────────────────────
    def test_remove_used_archives(self):
        self._add_activity()
        self.assertEqual(lifecycle.remove_lesson(self.lesson), 'archived')
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.is_archived)

    def test_remove_unused_deletes(self):
        lid = self.lesson.pk
        self.assertEqual(lifecycle.remove_lesson(self.lesson), 'deleted')
        self.assertFalse(Lesson.objects.filter(pk=lid).exists())
