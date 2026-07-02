"""Tests de l'édition versionnée — Phase 1 (brouillon mutable + versions immuables).

Prouve les 5 invariants :
  1. une version publiée n'est jamais mutée (append-only) ;
  2. publier crée exactement UNE nouvelle version, numérotation atomique ;
  3. la progression élève (PROTECT) sur une ancienne version survit à une publication ;
  4. le brouillon est invisible aux élèves (le live ne bouge qu'au publish) ;
  5. éditer sans publier ne change RIEN pour l'élève.

Lancement : python manage.py test apps.lessons.tests_versioning
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.lessons.models import Lesson, LessonContentVersion, LessonContentDraft, LessonStatus
from apps.lessons import versioning

User = get_user_model()


class VersioningTest(TestCase):

    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70009001', full_name='Prof Test', password='x')
        self.lesson = Lesson.objects.create(
            teacher=self.teacher, title='Le relief', subject='Géographie',
            level='fondamental_2', format_version=2, status=LessonStatus.READY,
        )
        self.v1 = LessonContentVersion.objects.create(
            lesson=self.lesson, version=1,
            concepts_data=[{'id': 'c1', 'name': "Vue d'ensemble"}],
            exam_data={'pass_mark': 0.6, 'questions': []},
            color='#111111', guide='Sory',
        )
        self.lesson.active_content_version = self.v1
        self.lesson.save(update_fields=['active_content_version'])

    # ── open_draft ────────────────────────────────────────────────────────────
    def test_open_draft_copies_live(self):
        draft = versioning.open_draft(self.lesson)
        self.assertEqual(draft.based_on_version, 1)
        self.assertEqual(draft.guide, 'Sory')
        self.assertEqual(draft.concepts_data, [{'id': 'c1', 'name': "Vue d'ensemble"}])
        # idempotent : ré-ouvrir renvoie le même brouillon
        self.assertEqual(versioning.open_draft(self.lesson).pk, draft.pk)

    def test_open_draft_without_live(self):
        lesson = Lesson.objects.create(
            teacher=self.teacher, title='Vierge', subject='X', format_version=2)
        draft = versioning.open_draft(lesson)
        self.assertIsNone(draft.based_on_version)
        self.assertIsNone(draft.concepts_data)

    # ── invariants 1, 4, 5 : éditer ne touche pas le live ──────────────────────
    def test_edit_draft_does_not_touch_live(self):
        versioning.edit_draft(self.lesson, guide='Awa')
        draft = LessonContentDraft.objects.get(lesson=self.lesson)
        self.assertEqual(draft.guide, 'Awa')

        # La version publiée est INCHANGÉE (invariant 1).
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.guide, 'Sory')
        # Le live n'a PAS bougé (invariants 4 & 5).
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.active_content_version_id, self.v1.id)

    # ── invariants 1 & 2 : publier crée v2, bascule, fige v1 ───────────────────
    def test_publish_creates_v2_and_switches_live(self):
        versioning.edit_draft(self.lesson, guide='Awa')
        v2 = versioning.publish_draft(self.lesson)

        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.guide, 'Awa')
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.active_content_version_id, v2.id)      # bascule
        self.assertEqual(self.lesson.content_versions.count(), 2)           # append-only
        # v1 figée, contenu intact (invariant 1)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.guide, 'Sory')
        # brouillon consommé
        self.assertFalse(LessonContentDraft.objects.filter(lesson=self.lesson).exists())

    def test_publish_without_draft_raises(self):
        with self.assertRaises(ValueError):
            versioning.publish_draft(self.lesson)

    def test_sequential_publishes_increment_version(self):
        versioning.edit_draft(self.lesson, guide='Awa')
        versioning.publish_draft(self.lesson)
        versioning.edit_draft(self.lesson, guide='Bina')
        v3 = versioning.publish_draft(self.lesson)
        self.assertEqual(v3.version, 3)
        self.assertEqual(self.lesson.content_versions.count(), 3)
        # un nouveau brouillon repart de la NOUVELLE live (v2)
        draft = versioning.open_draft(self.lesson)
        self.assertEqual(draft.based_on_version, 3)

    # ── invariant 3 : la progression élève (PROTECT) survit ────────────────────
    def test_student_progress_survives_publish(self):
        from apps.schools.models import School, SchoolClass
        from apps.students.models import Student
        from apps.student_learning.models import ConceptProgress

        school = School.objects.create(name='École Test', city='Bamako')
        sclass = SchoolClass.objects.create(
            school=school, name='6A', level='fondamental_2', annual_fee=0)
        student = Student.objects.create(
            school=school, school_class=sclass, full_name='Élève Test', tuition_fee=0)
        cp = ConceptProgress.objects.create(
            student=student, lesson=self.lesson, content_version=self.v1,
            concept_id='c1', passes_done=1)

        versioning.edit_draft(self.lesson, guide='Awa')
        versioning.publish_draft(self.lesson)

        cp.refresh_from_db()
        self.assertEqual(cp.content_version_id, self.v1.id)                 # toujours v1
        self.assertTrue(LessonContentVersion.objects.filter(pk=self.v1.pk).exists())

    # ── discard ────────────────────────────────────────────────────────────────
    def test_discard_draft(self):
        versioning.edit_draft(self.lesson, guide='Awa')
        versioning.discard_draft(self.lesson)
        self.assertFalse(LessonContentDraft.objects.filter(lesson=self.lesson).exists())
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.active_content_version_id, self.v1.id)  # live intact
        # idempotent
        versioning.discard_draft(self.lesson)
