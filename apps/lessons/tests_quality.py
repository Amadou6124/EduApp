"""Tests du contrôle qualité — Phase 3 (déterministe exhaustif + critique IA mockée).

Lancement : python manage.py test apps.lessons.tests_quality
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.lessons import quality


VALID = {
    'concepts': [{
        'id': 'c1', 'name': 'Concept 1',
        'quiz': [
            {'id': 'q1', 'type': 'mcq_single', 'options': ['a', 'b', 'c'], 'answer_indices': [0]},
            {'id': 'q2', 'type': 'ordering', 'items': ['x', 'y', 'z'], 'correct_order': [2, 0, 1]},
        ],
    }],
    'exam': {'pass_mark': 0.6, 'questions': [
        {'id': 'e1', 'concept_id': 'c1', 'type': 'mcq_single',
         'options': ['a', 'b'], 'answer_indices': [1]},
    ]},
}


class StructuralCheckTest(SimpleTestCase):

    def test_valid_content_no_flags(self):
        self.assertEqual(quality.structural_check(VALID), [])

    def _codes(self, content):
        return {f['code'] for f in quality.structural_check(content)}

    def test_exam_bad_concept_ref(self):
        c = {'concepts': [{'id': 'c1'}],
             'exam': {'pass_mark': 0.6, 'questions': [{'id': 'e1', 'concept_id': 'cX'}]}}
        self.assertIn('bad_ref', self._codes(c))

    def test_answer_index_out_of_bounds(self):
        c = {'concepts': [{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': ['a', 'b'], 'answer_indices': [5]}]}]}
        self.assertIn('index_oob', self._codes(c))

    def test_ordering_not_a_permutation(self):
        c = {'concepts': [{'id': 'c1', 'quiz': [
            {'id': 'q1', 'items': ['x', 'y', 'z'], 'correct_order': [0, 0, 1]}]}]}
        self.assertIn('bad_order', self._codes(c))

    def test_pass_mark_invalid(self):
        c = {'concepts': [{'id': 'c1'}], 'exam': {'pass_mark': 1.5, 'questions': []}}
        self.assertIn('pass_mark', self._codes(c))

    def test_no_answer_marked(self):
        c = {'concepts': [{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': ['a', 'b'], 'answer_indices': []}]}]}
        self.assertIn('no_answer', self._codes(c))

    def test_empty_options(self):
        c = {'concepts': [{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': [], 'answer_indices': []}]}]}
        self.assertIn('empty_options', self._codes(c))

    def test_robust_on_garbage(self):
        # Ne crash pas sur des formes inattendues.
        self.assertEqual(quality.structural_check({}), [])
        self.assertEqual(quality.structural_check({'concepts': ['pas un dict']}), [])


class AiQualityCheckTest(SimpleTestCase):

    def test_no_source_skips_ai(self):
        with patch.object(quality, 'call_critique') as m:
            self.assertEqual(quality.ai_quality_check(VALID, None), [])
            m.assert_not_called()

    def test_normalizes_ai_flags(self):
        payload = {'flags': [{'item_id': 'q1', 'concept_id': 'c1',
                              'block': 'concepts', 'reason': 'Réponse fausse'}]}
        with patch.object(quality, 'call_critique', return_value=payload):
            flags = quality.ai_quality_check(VALID, 'source')
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]['severity'], 'warn')
        self.assertEqual(flags[0]['code'], 'ai_doubt')
        self.assertEqual(flags[0]['item_id'], 'q1')

    def test_ai_failure_is_fail_safe(self):
        with patch.object(quality, 'call_critique', side_effect=RuntimeError('boom')):
            self.assertEqual(quality.ai_quality_check(VALID, 'source'), [])


class QualityCheckTest(SimpleTestCase):

    def test_errors_sorted_before_warnings(self):
        broken = {'concepts': [{'id': 'c1', 'quiz': [
            {'id': 'q1', 'options': ['a'], 'answer_indices': [9]}]}],
            'exam': {'pass_mark': 0.6, 'questions': []}}
        ai_payload = {'flags': [{'item_id': 'q1', 'block': 'concepts', 'reason': 'doute'}]}
        with patch.object(quality, 'call_critique', return_value=ai_payload):
            flags = quality.quality_check(broken, 'source')
        self.assertGreaterEqual(len(flags), 2)
        self.assertEqual(flags[0]['severity'], 'error')   # error d'abord
        self.assertEqual(flags[-1]['severity'], 'warn')
