"""Tests des vues v2 (upload d'unité) — Django test Client, sans API ni threads réels.

call_architect / launch_unit_generation / extraction sont MOCKÉS (patch sur le
namespace apps.lessons.views, où ils sont importés). MEDIA_ROOT temporaire pour ne
pas polluer le media de dev. Lancement : python manage.py test apps.lessons.tests_views_v2
"""
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.lessons.models import Unit, LessonStatus
from apps.lessons import services
from apps.schools.models import School

User = get_user_model()

ARCH = {
    'unit_title': 'Géographie du Mali', 'subject': 'Histoire-Géographie', 'direction': 'ltr',
    'lessons': [
        {'id': 'le-relief', 'title': 'Le relief', 'summary': 'Résumé relief.'},
        {'id': 'le-climat', 'title': 'Le climat', 'summary': 'Résumé climat.'},
    ],
}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class UnitViewsV2Test(TestCase):

    def setUp(self):
        self.school = School.objects.create(name='École Test', city='Bamako')
        self.teacher = User.objects.create_user(
            phone_number='70001000', full_name='Prof V2', password='x')
        self.teacher.is_superuser = True       # passe teacher_required
        self.teacher.school = self.school      # fallback get_school (legacy)
        self.teacher.save()
        self.client.force_login(self.teacher)

    def _skeleton(self, teacher=None):
        return services._create_unit_skeleton(
            ARCH, teacher=teacher or self.teacher, school=self.school,
            initial_status=LessonStatus.DRAFT)

    # ── unit_upload ─────────────────────────────────────────────────────────────
    def test_upload_creates_skeleton_draft_no_generation(self):
        f = SimpleUploadedFile('doc.txt', b'contenu', content_type='text/plain')
        with patch('apps.lessons.views.validate_lesson_file', return_value='text'), \
             patch('apps.lessons.views.extract_content_from_file', return_value='doc'), \
             patch('apps.lessons.views.call_architect', return_value=ARCH), \
             patch('apps.lessons.views.launch_unit_generation') as m_launch:
            resp = self.client.post(reverse('lessons:unit-upload'), {
                'source_file': f,
                'selected_subject_name': 'Géographie',
                'selected_subject_type': 'geography',
                'selected_level': 'fondamental_2',
            })
        self.assertEqual(resp.status_code, 302)            # redirect détail
        unit = Unit.objects.get()
        self.assertEqual(unit.status, LessonStatus.DRAFT)  # confirmer-lite
        self.assertEqual(unit.lessons.count(), 2)
        for l in unit.lessons.all():
            self.assertEqual(l.status, LessonStatus.DRAFT)  # initial_status=DRAFT
        m_launch.assert_not_called()                        # PAS de génération auto

    def test_upload_unreadable_no_skeleton(self):
        f = SimpleUploadedFile('doc.txt', b'flou', content_type='text/plain')
        with patch('apps.lessons.views.validate_lesson_file', return_value='text'), \
             patch('apps.lessons.views.extract_content_from_file', return_value='doc'), \
             patch('apps.lessons.views.call_architect',
                   return_value={'error': 'unreadable', 'message': 'Document flou'}):
            resp = self.client.post(reverse('lessons:unit-upload'), {
                'source_file': f, 'selected_subject_name': 'Géographie',
            })
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(Unit.objects.count(), 0)          # aucun skeleton créé
        self.assertContains(resp, 'Document flou', status_code=422)

    def test_upload_no_file(self):
        resp = self.client.post(reverse('lessons:unit-upload'),
                                {'selected_subject_name': 'Géographie'})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(Unit.objects.count(), 0)

    # ── unit_generate ───────────────────────────────────────────────────────────
    def test_generate_launches(self):
        unit = self._skeleton()
        with patch('apps.lessons.views.launch_unit_generation', return_value=True) as m:
            resp = self.client.post(reverse('lessons:unit-generate', args=[unit.id]))
        self.assertEqual(resp.status_code, 200)
        m.assert_called_once()
        self.assertIn('"type": "info"', resp['HX-Trigger'])     # lancée

    def test_generate_already_running(self):
        unit = self._skeleton()
        with patch('apps.lessons.views.launch_unit_generation', return_value=False):
            resp = self.client.post(reverse('lessons:unit-generate', args=[unit.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('"type": "warning"', resp['HX-Trigger'])  # déjà en cours

    def test_generate_other_teacher_404(self):
        other = User.objects.create_user(
            phone_number='70002000', full_name='Autre', password='x')
        unit = self._skeleton(teacher=other)
        with patch('apps.lessons.views.launch_unit_generation') as m:
            resp = self.client.post(reverse('lessons:unit-generate', args=[unit.id]))
        self.assertEqual(resp.status_code, 404)
        m.assert_not_called()

    # ── unit_status (polling) ────────────────────────────────────────────────────
    def test_status_partial_while_active(self):
        unit = self._skeleton()
        services._acquire_generation_lock(unit)   # verrou frais → génération active
        resp = self.client.get(reverse('lessons:unit-status', args=[unit.id]),
                               HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Le relief')     # checklist rendue

    def test_status_terminal_refresh(self):
        unit = self._skeleton()                    # pas de verrou → terminal
        resp = self.client.get(reverse('lessons:unit-status', args=[unit.id]),
                               HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp['HX-Refresh'], 'true')

    # ── unit_detail (rendu) ──────────────────────────────────────────────────────
    def test_detail_shows_launch_button(self):
        unit = self._skeleton()
        resp = self.client.get(reverse('lessons:unit-detail', args=[unit.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Lancer la génération')   # pas de verrou → bouton
