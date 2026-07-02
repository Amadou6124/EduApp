"""Tests de l'édition versionnée — Phase 1 (brouillon mutable + versions immuables).

Prouve les 5 invariants :
  1. une version publiée n'est jamais mutée (append-only) ;
  2. publier crée exactement UNE nouvelle version, numérotation atomique ;
  3. la progression élève (PROTECT) sur une ancienne version survit à une publication ;
  4. le brouillon est invisible aux élèves (le live ne bouge qu'au publish) ;
  5. éditer sans publier ne change RIEN pour l'élève.

Lancement : python manage.py test apps.lessons.tests_versioning
"""
from unittest.mock import patch

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


class RegenBlockTest(TestCase):
    """Phase 2 — régénération ciblée d'un bloc (IA mockée, 0 appel réel)."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70009002', full_name='Prof Test', password='x')
        self.lesson = Lesson.objects.create(
            teacher=self.teacher, title='Le relief', summary='Résumé',
            subject='Géographie', level='fondamental_2',
            format_version=2, status=LessonStatus.READY,
        )
        self.v1 = LessonContentVersion.objects.create(
            lesson=self.lesson, version=1,
            concepts_data=[{'id': 'c1', 'name': 'Concept 1'}],
            reading_data={'title': 'Lecture 1'},
            exam_data={'pass_mark': 0.6, 'questions': []},
            story_data={'scene': 'v1'},
            color='#111111', guide='Sory',
        )
        self.lesson.active_content_version = self.v1
        self.lesson.save(update_fields=['active_content_version'])

    def _assert_live_unchanged(self):
        """Aucune publication : le live reste v1, aucune nouvelle version."""
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.active_content_version_id, self.v1.id)
        self.assertEqual(self.lesson.content_versions.count(), 1)

    def test_regen_noyau_writes_draft_only(self):
        noyau = {'color': '#222', 'guide': 'Awa',
                 'concepts': [{'id': 'c1', 'name': 'Concept RÉVISÉ'}],
                 'exam': {'pass_mark': 0.7, 'questions': [{'id': 'e1'}]}}
        with patch.object(versioning_services(), 'call_noyau', return_value=noyau):
            versioning.regenerate_block(self.lesson, 'noyau', source='doc')

        draft = LessonContentDraft.objects.get(lesson=self.lesson)
        self.assertEqual(draft.concepts_data, noyau['concepts'])
        self.assertEqual(draft.exam_data, noyau['exam'])
        self.assertEqual(draft.guide, 'Awa')
        # les autres blocs restent hérités de la live
        self.assertEqual(draft.reading_data, {'title': 'Lecture 1'})
        self.assertEqual(draft.story_data, {'scene': 'v1'})
        self._assert_live_unchanged()

    def test_regen_lecture_only_touches_reading(self):
        with patch.object(versioning_services(), 'call_lecture',
                          return_value={'reading': {'title': 'Lecture RÉVISÉE'}}):
            versioning.regenerate_block(self.lesson, 'lecture', source='doc')

        draft = LessonContentDraft.objects.get(lesson=self.lesson)
        self.assertEqual(draft.reading_data, {'title': 'Lecture RÉVISÉE'})
        # concepts inchangés (hérités de la live)
        self.assertEqual(draft.concepts_data, [{'id': 'c1', 'name': 'Concept 1'}])
        self._assert_live_unchanged()

    def test_regen_histoire_uses_current_concepts(self):
        svc = versioning_services()
        with patch.object(svc, 'call_histoire',
                          return_value={'story': {'scene': 'RÉVISÉE'}}) as m:
            versioning.regenerate_block(self.lesson, 'histoire', source='doc')

        # call_histoire a reçu les concepts + guide COURANTS (copiés de la live)
        _, kwargs = m.call_args
        self.assertEqual(kwargs['concepts'], [{'id': 'c1', 'name': 'Concept 1'}])
        self.assertEqual(kwargs['guide'], 'Sory')
        draft = LessonContentDraft.objects.get(lesson=self.lesson)
        self.assertEqual(draft.story_data, {'scene': 'RÉVISÉE'})
        self._assert_live_unchanged()

    def test_regen_then_publish_merges_correctly(self):
        noyau = {'color': '#222', 'guide': 'Awa',
                 'concepts': [{'id': 'c1', 'name': 'RÉVISÉ'}], 'exam': {'pass_mark': 0.7}}
        with patch.object(versioning_services(), 'call_noyau', return_value=noyau):
            versioning.regenerate_block(self.lesson, 'noyau', source='doc')
        v2 = versioning.publish_draft(self.lesson)

        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.concepts_data, noyau['concepts'])   # bloc régénéré
        self.assertEqual(v2.reading_data, {'title': 'Lecture 1'})  # bloc hérité
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.active_content_version_id, v2.id)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.concepts_data, [{'id': 'c1', 'name': 'Concept 1'}])  # v1 figée

    def test_regen_invalid_block_raises(self):
        with self.assertRaises(ValueError):
            versioning.regenerate_block(self.lesson, 'exam', source='doc')

    def test_regen_adds_cost(self):
        from decimal import Decimal

        def _noyau(*a, cost_sink=None, **k):
            if cost_sink is not None:
                cost_sink.append(Decimal('0.0007'))
            return {'color': '#222', 'guide': 'Awa', 'concepts': [], 'exam': {}}

        with patch.object(versioning_services(), 'call_noyau', side_effect=_noyau):
            versioning.regenerate_block(self.lesson, 'noyau', source='doc')

        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.generation_cost_usd, Decimal('0.0007'))


def versioning_services():
    """Le module services vu par versioning.regenerate_block (pour patcher les call_*)."""
    from apps.lessons import services
    return services
