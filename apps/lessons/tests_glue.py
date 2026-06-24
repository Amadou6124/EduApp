"""Tests de la glue génération↔persistance (PORTAL_V2_SPEC, Phase B).

Base temporaire Django (TestCase) — aucune génération IA : l'objet `generated`
(§3.1) est fabriqué à la main. Aucun appel API, aucune pollution de la base de dev.

Lancement : python manage.py test apps.lessons.tests_glue
"""
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.lessons.models import Unit, Lesson, LessonContentVersion, LessonStatus
from apps.lessons import services

User = get_user_model()

# Structure Architecte factice (2 leçons).
ARCHITECT = {
    'unit_title': 'Géographie du Mali',
    'subject': 'Histoire-Géographie — 6ème',
    'direction': 'ltr',
    'lessons': [
        {'id': 'le-relief', 'title': 'Le relief', 'summary': 'Résumé relief.'},
        {'id': 'le-climat', 'title': 'Le climat', 'summary': 'Résumé climat.'},
    ],
}

# Objet leçon assemblé (§3.1) factice — ce que produirait generate_lesson_v2.
GENERATED = {
    'id': 'le-relief', 'title': 'Le relief', 'subject': 'X', 'direction': 'ltr',
    'color': '#D97706', 'guide': 'Sory',
    'concepts': [{'id': 'c1', 'name': "Vue d'ensemble", 'passes': 1, 'quiz': []}],
    'exam': {'pass_mark': 0.6, 'questions': [{'id': 'e1', 'concept_id': 'c1', 'type': 'mcq_single'}]},
    'reading': {'title': 'Le relief', 'sections': [{'id': 's1', 'blocks': []}]},
    'story': {'scene': {'name': 'Voyage'}, 'characters': [], 'steps': []},
}


class GlueHelpersTest(TestCase):

    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70000000', full_name='Prof Test', password='x')

    # ── _create_unit_skeleton ──────────────────────────────────────────────────
    def test_create_unit_skeleton(self):
        unit = services._create_unit_skeleton(ARCHITECT, teacher=self.teacher, school=None)

        self.assertEqual(unit.status, LessonStatus.PROCESSING)
        self.assertEqual(unit.title, 'Géographie du Mali')
        self.assertEqual(unit.subject, 'Histoire-Géographie — 6ème')
        self.assertEqual(unit.direction, 'ltr')

        lessons = list(unit.lessons.order_by('id'))
        self.assertEqual(len(lessons), 2)
        for shell, meta in zip(lessons, ARCHITECT['lessons']):
            self.assertEqual(shell.status, LessonStatus.PROCESSING)
            self.assertEqual(shell.format_version, 2)
            self.assertEqual(shell.title, meta['title'])
            self.assertEqual(shell.summary, meta['summary'])
            self.assertEqual(shell.slug, meta['id'])
            self.assertEqual(shell.unit_id, unit.id)
            self.assertIsNone(shell.active_content_version_id)

    def test_create_unit_skeleton_is_atomic(self):
        """Une structure sans 'lessons' valides → aucune Unit ne doit subsister."""
        bad = {'unit_title': 'X', 'subject': 'Y', 'direction': 'ltr'}  # pas de 'lessons'
        before = Unit.objects.count()
        with self.assertRaises(KeyError):
            services._create_unit_skeleton(bad, teacher=self.teacher)
        self.assertEqual(Unit.objects.count(), before)  # rollback : rien de créé

    # ── _persist_lesson_version (v1 puis v2) ───────────────────────────────────
    def test_persist_lesson_version_v1_then_v2(self):
        unit = services._create_unit_skeleton(ARCHITECT, teacher=self.teacher)
        lesson = unit.lessons.order_by('id').first()

        # v1
        cv1 = services._persist_lesson_version(lesson, GENERATED, Decimal('0.0012'))
        lesson.refresh_from_db()
        self.assertEqual(cv1.version, 1)
        self.assertEqual(lesson.status, LessonStatus.READY)
        self.assertEqual(lesson.active_content_version_id, cv1.id)
        # remap des clés
        self.assertEqual(cv1.concepts_data, GENERATED['concepts'])
        self.assertEqual(cv1.reading_data, GENERATED['reading'])
        self.assertEqual(cv1.exam_data, GENERATED['exam'])
        self.assertEqual(cv1.color, '#D97706')
        self.assertEqual(cv1.guide, 'Sory')
        self.assertEqual(cv1.generation_cost_usd, Decimal('0.0012'))

        # v2 (régénération) : nouvelle version, bascule du pointeur, v1 intacte
        cv2 = services._persist_lesson_version(lesson, GENERATED, Decimal('0.0005'))
        lesson.refresh_from_db()
        self.assertEqual(cv2.version, 2)
        self.assertEqual(lesson.active_content_version_id, cv2.id)  # bascule
        cv1.refresh_from_db()
        self.assertEqual(cv1.version, 1)                            # v1 inchangée
        self.assertEqual(lesson.content_versions.count(), 2)

    # ── _finalize_unit_status (3 cas) ──────────────────────────────────────────
    def test_finalize_all_ready(self):
        unit = services._create_unit_skeleton(ARCHITECT, teacher=self.teacher)
        for l in unit.lessons.all():
            services._persist_lesson_version(l, GENERATED, Decimal('0'))
        services._finalize_unit_status(unit)
        unit.refresh_from_db()
        self.assertEqual(unit.status, LessonStatus.READY)

    def test_finalize_mixed_partial(self):
        unit = services._create_unit_skeleton(ARCHITECT, teacher=self.teacher)
        first = unit.lessons.order_by('id').first()
        services._persist_lesson_version(first, GENERATED, Decimal('0'))
        other = unit.lessons.exclude(id=first.id).first()
        other.status = LessonStatus.ERROR
        other.save(update_fields=['status'])
        services._finalize_unit_status(unit)
        unit.refresh_from_db()
        self.assertEqual(unit.status, LessonStatus.PARTIAL)

    def test_finalize_none_ready_error(self):
        unit = services._create_unit_skeleton(ARCHITECT, teacher=self.teacher)
        for l in unit.lessons.all():
            l.status = LessonStatus.ERROR
            l.save(update_fields=['status'])
        services._finalize_unit_status(unit)
        unit.refresh_from_db()
        self.assertEqual(unit.status, LessonStatus.ERROR)
