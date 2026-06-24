"""Tests de la glue génération↔persistance (PORTAL_V2_SPEC, Phase B).

Base temporaire Django (TestCase) — aucune génération IA : l'objet `generated`
(§3.1) est fabriqué à la main. Aucun appel API, aucune pollution de la base de dev.

Lancement : python manage.py test apps.lessons.tests_glue
"""
import os
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.lessons.models import (Unit, Lesson, LessonContentVersion, LessonStatus,
                                 SubjectType, EducationLevel)
from apps.lessons import services

User = get_user_model()

DOC_PATH = Path(__file__).resolve().parents[2] / 'test_docs' / 'geographie_mali_test.txt'

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
    'story': {
        'scene': {'name': 'Au marché', 'c1': '#F97316', 'c2': '#BE123C'},
        'characters': [{'id': 'sory', 'name': 'Sory', 'role': 'Guide', 'side': 'left'}],
        'steps': [
            {'type': 'narration', 'text': 'Sory observe les plateaux.'},
            {'type': 'npc', 'who': 'sory', 'text': 'Le relief du Mali est varié.', 'concept_ref': 'c1'},
        ],
    },
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
        self.assertEqual(cv1.story_data, GENERATED['story'])   # story bien persistée
        self.assertTrue(cv1.story_data['steps'])               # non vide
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


class PersistGeneratedUnitTest(TestCase):
    """Orchestration de création : generate_lesson_v2 est MOCKÉ (aucune API)."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70000001', full_name='Prof Test', password='x')

    def test_all_success(self):
        def fake_gen(lesson_meta, source, cost_sink=None):
            if cost_sink is not None:
                cost_sink.append(Decimal('0.001'))
            return GENERATED
        with patch.object(services, 'generate_lesson_v2', side_effect=fake_gen) as m:
            unit = services.persist_generated_unit(ARCHITECT, 'doc source', teacher=self.teacher)

        self.assertEqual(unit.status, LessonStatus.READY)
        self.assertEqual(m.call_count, 2)                  # 2 leçons générées
        for l in unit.lessons.all():
            self.assertEqual(l.status, LessonStatus.READY)
            self.assertIsNotNone(l.active_content_version_id)
            self.assertEqual(l.content_versions.count(), 1)   # v1 par leçon
        self.assertEqual(unit.generation_cost_usd, Decimal('0.002'))  # 2 × 0.001

    def test_partial_failure(self):
        """Leçon 'le-relief' réussit, 'le-climat' lève → l'une ready, l'autre error,
        Unit PARTIAL. La leçon réussie n'est PAS affectée par l'échec de l'autre."""
        def fake_gen(lesson_meta, source, cost_sink=None):
            if lesson_meta['id'] == 'le-relief':
                if cost_sink is not None:
                    cost_sink.append(Decimal('0.001'))
                return GENERATED
            raise services.LessonBlockError('B3', RuntimeError('529 simulé'))
        with patch.object(services, 'generate_lesson_v2', side_effect=fake_gen):
            unit = services.persist_generated_unit(ARCHITECT, 'doc', teacher=self.teacher)

        self.assertEqual(unit.status, LessonStatus.PARTIAL)

        relief = unit.lessons.get(slug='le-relief')
        self.assertEqual(relief.status, LessonStatus.READY)
        self.assertIsNotNone(relief.active_content_version_id)
        self.assertEqual(relief.content_versions.count(), 1)   # v1 intacte

        climat = unit.lessons.get(slug='le-climat')
        self.assertEqual(climat.status, LessonStatus.ERROR)
        self.assertIsNone(climat.active_content_version_id)
        self.assertEqual(climat.content_versions.count(), 0)   # pas de version

        self.assertEqual(unit.generation_cost_usd, Decimal('0.001'))  # seule la réussie

    def test_all_failure(self):
        def fake_gen(lesson_meta, source, cost_sink=None):
            raise services.LessonBlockError('B1', RuntimeError('529 simulé'))
        with patch.object(services, 'generate_lesson_v2', side_effect=fake_gen):
            unit = services.persist_generated_unit(ARCHITECT, 'doc', teacher=self.teacher)

        self.assertEqual(unit.status, LessonStatus.ERROR)
        for l in unit.lessons.all():
            self.assertEqual(l.status, LessonStatus.ERROR)
            self.assertEqual(l.content_versions.count(), 0)
        self.assertEqual(unit.generation_cost_usd, Decimal('0'))


def _gen_ok(cost=Decimal('0.001'), **overrides):
    """Fabrique un side_effect de generate_lesson_v2 qui réussit (append coût + renvoie
    un §3.1 factice, éventuellement modifié)."""
    def fn(lesson_meta, source, cost_sink=None):
        if cost_sink is not None:
            cost_sink.append(cost)
        g = dict(GENERATED)
        g.update(overrides)
        return g
    return fn


class ResumeUnitTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70000002', full_name='Prof Test', password='x')

    def test_resume_completes_partial_idempotent(self):
        # État PARTIAL : le-relief ready, le-climat error.
        def gen_partial(meta, source, cost_sink=None):
            if meta['id'] == 'le-relief':
                if cost_sink is not None:
                    cost_sink.append(Decimal('0.001'))
                return GENERATED
            raise services.LessonBlockError('B3', RuntimeError('529 simulé'))
        with patch.object(services, 'generate_lesson_v2', side_effect=gen_partial):
            unit = services.persist_generated_unit(ARCHITECT, 'doc', teacher=self.teacher)
        self.assertEqual(unit.status, LessonStatus.PARTIAL)

        # Reprise : tout réussit maintenant.
        with patch.object(services, 'generate_lesson_v2',
                          side_effect=_gen_ok(cost=Decimal('0.002'))) as m:
            unit = services.resume_unit(unit, 'doc')

        # SEULE la leçon error a été régénérée (le-relief ready → sautée).
        self.assertEqual(m.call_count, 1)                      # idempotence
        self.assertEqual(unit.status, LessonStatus.READY)
        relief = unit.lessons.get(slug='le-relief')
        climat = unit.lessons.get(slug='le-climat')
        self.assertEqual(relief.content_versions.count(), 1)   # PAS de v2 parasite
        self.assertEqual(climat.status, LessonStatus.READY)
        self.assertEqual(climat.content_versions.count(), 1)   # v1 créée à la reprise
        self.assertEqual(unit.generation_cost_usd, Decimal('0.003'))  # 0.001 + 0.002


class RegenerateLessonTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            phone_number='70000003', full_name='Prof Test', password='x')
        with patch.object(services, 'generate_lesson_v2', side_effect=_gen_ok()):
            self.unit = services.persist_generated_unit(ARCHITECT, 'doc', teacher=self.teacher)
        self.lesson = self.unit.lessons.get(slug='le-relief')
        self.cv1 = self.lesson.active_content_version

    def test_regenerate_creates_v2_keeps_v1(self):
        with patch.object(services, 'generate_lesson_v2',
                          side_effect=_gen_ok(cost=Decimal('0.0005'), guide='Awa')):
            cv2 = services.regenerate_lesson(self.lesson, 'doc')

        self.lesson.refresh_from_db()
        self.assertEqual(cv2.version, 2)
        self.assertEqual(self.lesson.active_content_version_id, cv2.id)   # bascule
        self.assertEqual(self.lesson.content_versions.count(), 2)
        self.assertEqual(cv2.guide, 'Awa')
        # v1 toujours en base, contenu inchangé
        self.cv1.refresh_from_db()
        self.assertEqual(self.cv1.version, 1)
        self.assertEqual(self.cv1.guide, 'Sory')

    def test_regenerate_progression_survives(self):
        """Une progression pointant v1 (PROTECT) survit à la régénération."""
        from apps.schools.models import School, SchoolClass
        from apps.students.models import Student
        from apps.student_learning.models import ConceptProgress

        school = School.objects.create(name='École Test', city='Bamako')
        sclass = SchoolClass.objects.create(
            school=school, name='6A', level='fondamental_2', annual_fee=0)
        student = Student.objects.create(
            school=school, school_class=sclass, full_name='Élève Test', tuition_fee=0)
        cp = ConceptProgress.objects.create(
            student=student, lesson=self.lesson, content_version=self.cv1,
            concept_id='c1', passes_done=1)

        with patch.object(services, 'generate_lesson_v2', side_effect=_gen_ok()):
            services.regenerate_lesson(self.lesson, 'doc')

        cp.refresh_from_db()
        self.assertEqual(cp.content_version_id, self.cv1.id)   # toujours v1 (PROTECT a tenu)
        self.assertTrue(LessonContentVersion.objects.filter(pk=self.cv1.pk).exists())

    def test_regenerate_failure_keeps_ready(self):
        """Échec de régénération → la leçon RESTE ready avec sa v1 active (non dégradée)."""
        def gen_fail(meta, source, cost_sink=None):
            raise services.LessonBlockError('B1', RuntimeError('529 simulé'))
        with patch.object(services, 'generate_lesson_v2', side_effect=gen_fail):
            with self.assertRaises(services.LessonBlockError):
                services.regenerate_lesson(self.lesson, 'doc')

        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, LessonStatus.READY)             # pas dégradée
        self.assertEqual(self.lesson.active_content_version_id, self.cv1.id)  # v1 toujours active
        self.assertEqual(self.lesson.content_versions.count(), 1)            # pas de v2 fantôme


@skipUnless(os.environ.get('RUN_LIVE'), 'test live (vrais appels API) — activer avec RUN_LIVE=1')
class LiveEndToEndTest(TestCase):
    """Bout-à-bout RÉEL : call_architect + persist_generated_unit avec vraie génération.
    Base de test jetable (aucune pollution de dev). Tronqué à 1 leçon (~4 appels API)."""

    def test_live_relief(self):
        import anthropic
        from apps.schools.models import School

        contenu = DOC_PATH.read_text(encoding='utf-8')
        print(f'\n[LIVE] Document : {DOC_PATH.name} ({len(contenu)} car.)')

        # 1-2. Architecte (vrai appel)
        try:
            structure = call_architect = services.call_architect(contenu)
        except anthropic.APIError as e:
            self.skipTest(f'API Anthropic indisponible (Architecte) : {e}')
        if structure.get('error') == 'unreadable':
            self.skipTest(f"Architecte juge le doc illisible : {structure.get('message')}")
        print(f"[LIVE] Architecte : unit='{structure['unit_title']}', "
              f"{len(structure['lessons'])} leçons, subject='{structure['subject']}', "
              f"direction={structure['direction']}")

        # 3. Tronquer à la leçon relief (1 leçon → ~4 appels)
        relief = next((l for l in structure['lessons'] if 'relief' in l.get('id', '')),
                      structure['lessons'][0])
        structure['lessons'] = [relief]
        print(f"[LIVE] Leçon retenue : id={relief['id']} | title={relief['title']}")

        # 4. Fixtures + persistance réelle
        teacher = User.objects.create_user(
            phone_number='70009999', full_name='Prof Live', password='x')
        school = School.objects.create(name='École Live', city='Bamako')
        try:
            unit = services.persist_generated_unit(
                structure, contenu, teacher=teacher, school=school,
                subject_type=SubjectType.GEOGRAPHY, level=EducationLevel.FONDAMENTAL_2,
            )
        except anthropic.APIError as e:
            self.skipTest(f'API Anthropic indisponible (génération) : {e}')

        unit.refresh_from_db()
        if unit.status == LessonStatus.ERROR:
            self.skipTest('Toutes les leçons en ERROR (probable outage API durant la génération)')

        # 6. Vérifications DEPUIS LA BASE
        print(f"[LIVE] Unit.status={unit.status} | cost=${unit.generation_cost_usd}")
        self.assertEqual(unit.status, LessonStatus.READY)
        self.assertEqual(unit.lessons.count(), 1)

        lesson = unit.lessons.get()
        self.assertEqual(lesson.status, LessonStatus.READY)
        self.assertIsNotNone(lesson.active_content_version_id)

        cv = lesson.active_content_version
        print(f"[LIVE] Version v{cv.version} | color={cv.color} | guide={cv.guide} "
              f"| cost=${cv.generation_cost_usd}")
        print(f"[LIVE] concepts={len(cv.concepts_data)} | "
              f"reading.sections={len(cv.reading_data.get('sections', []))} | "
              f"exam.questions={len(cv.exam_data.get('questions', []))} | "
              f"story.steps={len(cv.story_data.get('steps', []))}")

        self.assertEqual(cv.version, 1)
        self.assertTrue(cv.concepts_data, 'concepts_data vide')
        self.assertTrue(cv.reading_data, 'reading_data vide')
        self.assertTrue(cv.exam_data, 'exam_data vide')
        self.assertTrue(cv.story_data, 'story_data vide (le fix B3 ne marche pas)')
        self.assertTrue(cv.color)
        self.assertTrue(cv.guide)
        self.assertGreater(cv.generation_cost_usd, 0)   # coût réel remonté
        self.assertGreater(unit.generation_cost_usd, 0)

        # Cohérence B1↔B3 relue DEPUIS LA BASE
        concept_ids = {c['id'] for c in cv.concepts_data}
        char_names = [c.get('name') for c in cv.story_data.get('characters', [])]
        print(f"[LIVE] cohérence : guide '{cv.guide}' in characters {char_names} ? "
              f"{cv.guide in char_names}")
        self.assertIn(cv.guide, char_names)
        refs = [s.get('concept_ref') for s in cv.story_data.get('steps', []) if s.get('concept_ref')]
        print(f"[LIVE] concept_ref de story : {refs} | concepts B1 : {sorted(concept_ids)}")
        for r in refs:
            self.assertIn(r, concept_ids, f"concept_ref '{r}' absent de concepts_data")
        print('[LIVE] OK — chaîne A↔B validée en réel, story persistée.')
