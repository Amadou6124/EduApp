"""Tests de la bibliothèque « Mes leçons » — Phase 8.

Prouve : le statut par unité (validée / à valider / archivée), les filtres, la
recherche, et l'archivage par unité (dépublie + réversible). Le rendu HTMX est
vérifié en preview ; ici on cible la logique de _library_context + les endpoints.

Lancement : python manage.py test apps.lessons.tests_library
"""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.lessons.models import (
    Unit, Lesson, LessonContentVersion, LessonDeployment, LessonStatus)
from apps.schools.models import School, SchoolClass

User = get_user_model()


class LibraryTest(TestCase):

    def setUp(self):
        self.school = School.objects.create(name='École Test', city='Bamako')
        self.teacher = User.objects.create_user(
            phone_number='70003000', full_name='Prof', password='x')
        self.teacher.is_superuser = True          # passe teacher_required
        self.teacher.school = self.school
        self.teacher.save()
        self.client.force_login(self.teacher)
        self.sclass = SchoolClass.objects.create(
            school=self.school, name='1ère A', level='fondamental_1', annual_fee=0)

    def _unit(self, title, subject='Français', status=LessonStatus.READY):
        u = Unit.objects.create(
            teacher=self.teacher, school=self.school, title=title,
            subject=subject, level='fondamental_1', status=status)
        return u

    def _lesson(self, unit, *, validated=False, status=LessonStatus.READY,
                archived=False, deployed=False):
        l = Lesson.objects.create(
            teacher=self.teacher, unit=unit, title=unit.title, subject=unit.subject,
            level='fondamental_1', format_version=2, status=status, is_archived=archived)
        cv = LessonContentVersion.objects.create(lesson=l, version=1)
        if validated:
            from django.utils import timezone
            cv.validated_by = self.teacher
            cv.validated_at = timezone.now()
            cv.save(update_fields=['validated_by', 'validated_at'])
        l.active_content_version = cv
        l.save(update_fields=['active_content_version'])
        if deployed:
            LessonDeployment.objects.create(
                lesson=l, school=self.school, school_class=self.sclass,
                deployed_by=self.teacher, is_active=True)
        return l

    # ── statut + filtres ────────────────────────────────────────────────────
    def test_statuses_and_counts(self):
        u_ready = self._unit('Les phrases')
        self._lesson(u_ready, validated=True, deployed=True)
        u_todo = self._unit('Les chiffres', subject='Maths')
        self._lesson(u_todo, validated=False)
        u_arch = self._unit('Vieux cours')
        self._lesson(u_arch, validated=True, archived=True)

        resp = self.client.get(reverse('lessons:unit-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '✓ validée')
        self.assertContains(resp, 'À valider')
        self.assertContains(resp, '1ère A')                 # classe déployée affichée
        self.assertNotContains(resp, 'Vieux cours')         # archivée masquée par défaut
        self.assertEqual(resp.context['counts']['to_validate'], 1)
        self.assertEqual(resp.context['counts']['ready'], 1)
        self.assertEqual(resp.context['counts']['archived'], 1)

    def test_filter_archived_shows_only_archived(self):
        u_ready = self._unit('Les phrases')
        self._lesson(u_ready, validated=True)
        u_arch = self._unit('Vieux cours')
        self._lesson(u_arch, archived=True)

        resp = self.client.get(reverse('lessons:unit-list'), {'filter': 'archived'})
        self.assertContains(resp, 'Vieux cours')
        self.assertNotContains(resp, 'Les phrases')

    def test_search_filters_by_title(self):
        self._lesson(self._unit('Les phrases'))
        self._lesson(self._unit('La division', subject='Maths'))
        resp = self.client.get(reverse('lessons:unit-list'), {'q': 'division'})
        self.assertContains(resp, 'La division')
        self.assertNotContains(resp, 'Les phrases')

    # ── archive / restauration ───────────────────────────────────────────────
    def test_archive_unit_undeploys_and_hides(self):
        u = self._unit('Les phrases')
        self._lesson(u, validated=True, deployed=True)
        resp = self.client.post(reverse('lessons:unit-archive', args=[u.id]),
                                {'filter': 'all', 'q': ''}, HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(all(l.is_archived for l in u.lessons.all()))
        self.assertFalse(LessonDeployment.objects.filter(
            lesson__unit=u, is_active=True).exists())        # dépubliée
        self.assertNotContains(resp, 'Les phrases')          # hors filtre « all »

    def test_unarchive_restores(self):
        u = self._unit('Vieux cours')
        self._lesson(u, archived=True)
        resp = self.client.post(reverse('lessons:unit-unarchive', args=[u.id]),
                                {'filter': 'archived', 'q': ''}, HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(any(l.is_archived for l in u.lessons.all()))

    def test_archive_other_teacher_404(self):
        other = User.objects.create_user(
            phone_number='70004000', full_name='Autre', password='x')
        u = Unit.objects.create(teacher=other, school=self.school, title='X',
                                subject='Français', level='fondamental_1')
        resp = self.client.post(reverse('lessons:unit-archive', args=[u.id]))
        self.assertEqual(resp.status_code, 404)
