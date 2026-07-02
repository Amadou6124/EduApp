"""Tests du gate de révision/validation — Phase 6 (logique cœur, sans HTTP).

Le câblage vues + templates est vérifié en preview ; ici on prouve : non validée
tant qu'on n'a pas publié avec validateur ; erreurs structurelles = gate dur ;
review_flags = structurel frais + IA cachée (triés error avant warn).

Lancement : python manage.py test apps.lessons.tests_review
"""
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.lessons.models import Lesson, LessonContentVersion, LessonStatus
from apps.lessons import versioning, quality
from apps.lessons.views import _is_validated

User = get_user_model()


class ReviewGateTest(TestCase):

    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70009006', full_name='Prof', password='x')
        self.lesson = Lesson.objects.create(
            teacher=self.teacher, title='Le relief', subject='Géo',
            level='fondamental_2', format_version=2, status=LessonStatus.READY)
        self.v1 = LessonContentVersion.objects.create(
            lesson=self.lesson, version=1,
            concepts_data=[{'id': 'c1', 'name': 'C1', 'quiz': [
                {'id': 'q1', 'type': 'mcq_single', 'instruction': 'Q?', 'options': ['a', 'b'], 'answer_index': 0}]}],
            exam_data={'pass_mark': 0.6, 'questions': []})
        self.lesson.active_content_version = self.v1
        self.lesson.save(update_fields=['active_content_version'])

    def test_not_validated_after_generation(self):
        self.assertFalse(_is_validated(self.lesson))     # v1 sans tampon

    def test_validated_after_publish_with_validator(self):
        versioning.edit_draft(self.lesson, guide='x')
        versioning.publish_draft(self.lesson, validated_by=self.teacher)
        self.lesson.refresh_from_db()
        self.assertTrue(_is_validated(self.lesson))

    def test_blocking_errors_detects_structural(self):
        versioning.edit_draft(self.lesson, concepts_data=[{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': ['a', 'b'], 'answer_index': 9}]}])   # hors bornes
        errs = quality.blocking_errors(self.lesson)
        self.assertTrue(any(e['code'] == 'index_oob' for e in errs))

    def test_no_blocking_when_clean(self):
        versioning.edit_draft(self.lesson, concepts_data=[{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': ['a', 'b'], 'answer_index': 1}]}])
        self.assertEqual(quality.blocking_errors(self.lesson), [])

    def test_review_flags_merges_structural_and_cached_ai(self):
        versioning.edit_draft(self.lesson, concepts_data=[{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': ['a'], 'answer_index': 5}]}])          # erreur structurelle
        draft = versioning.open_draft(self.lesson)
        draft.ai_flags = [{'block': 'concepts', 'concept_id': 'c1', 'item_id': 'q1',
                           'severity': 'warn', 'code': 'ai_doubt', 'message': 'doute'}]
        draft.save(update_fields=['ai_flags'])
        flags = quality.review_flags(self.lesson)
        codes = {f['code'] for f in flags}
        self.assertIn('index_oob', codes)
        self.assertIn('ai_doubt', codes)
        self.assertEqual(flags[0]['severity'], 'error')    # error avant warn

    def test_compute_ai_flags_caches_on_draft(self):
        payload = [{'block': 'concepts', 'concept_id': 'c1', 'item_id': 'q1',
                    'severity': 'warn', 'code': 'ai_doubt', 'message': 'x'}]
        with patch.object(quality, 'ai_quality_check', return_value=payload):
            quality.compute_ai_flags(self.lesson)
        draft = versioning.open_draft(self.lesson)
        self.assertEqual(draft.ai_flags, payload)
