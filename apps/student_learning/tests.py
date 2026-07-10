"""Tests du portail élève — service de répétition espacée (srs.py).

Chaque test est hermétique (TestCase = transaction rollback automatique).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.lessons.models import (
    Lesson, LessonContentVersion, LessonDeployment, LessonStatus,
)
from apps.schools.models import (
    ClassSubject, CourseSlot, School, SchoolClass, SchoolYear, Subject,
)
from apps.students.models import Student

from . import srs
from .models import ConceptProgress, ConceptReview

User = get_user_model()


def _concepts():
    """2 concepts : c1 (1 passe, 2 quiz), c2 (2 passes, 2 quiz)."""
    return [
        {'id': 'c1', 'name': 'Concept Un', 'passes': 1, 'order': 1,
         'quiz': [
             {'id': 'q1', 'type': 'mcq_single', 'pass_index': 0,
              'instruction': 'Q1 ?', 'options': ['A', 'B'], 'answer_index': 0},
             {'id': 'q2', 'type': 'true_false', 'pass_index': 0,
              'instruction': 'Q2 ?', 'answer': True},
         ]},
        {'id': 'c2', 'name': 'Concept Deux', 'passes': 2, 'order': 2,
         'quiz': [
             {'id': 'q3', 'type': 'mcq_single', 'pass_index': 0,
              'instruction': 'Q3 ?', 'options': ['A', 'B'], 'answer_index': 1},
             {'id': 'q4', 'type': 'true_false', 'pass_index': 1,
              'instruction': 'Q4 ?', 'answer': False},
         ]},
    ]


class SRSBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            phone_number='79990199', password='x', full_name='Prof SRS',
        )
        cls.school = School.objects.create(
            name='École SRS', short_name='ES', city='Bamako', school_type='primary',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass,
            full_name='Adama Test', tuition_fee=Decimal('0'),
        )
        cls.lesson = Lesson.objects.create(
            teacher=cls.teacher, school=cls.school, title='Leçon SRS',
            subject='Français', format_version=2, status=LessonStatus.READY,
        )
        cls.cv = LessonContentVersion.objects.create(
            lesson=cls.lesson, version=1, concepts_data=_concepts(),
        )
        cls.lesson.active_content_version = cls.cv
        cls.lesson.save(update_fields=['active_content_version'])
        LessonDeployment.objects.create(
            lesson=cls.lesson, school=cls.school, school_class=cls.klass,
        )

    # helpers ------------------------------------------------------------
    def _complete(self, concept_id, passes_done=1, cv=None):
        return ConceptProgress.objects.create(
            student=self.student, lesson=self.lesson,
            content_version=cv or self.cv,
            concept_id=concept_id, passes_done=passes_done,
        )

    def _review(self, concept_id='c1', box=1, due=None, cv=None):
        return ConceptReview.objects.create(
            student=self.student, lesson=self.lesson,
            content_version=cv or self.cv, concept_id=concept_id,
            box=box, due_date=due or timezone.localdate(),
        )


class SyncReviewsTests(SRSBase):
    def test_concept_termine_entre_en_boite_1(self):
        self._complete('c1', passes_done=1)
        srs.sync_reviews(self.student)
        r = ConceptReview.objects.get(student=self.student, concept_id='c1')
        self.assertEqual(r.box, 1)
        # dû 2 jours après la complétion (aujourd'hui dans le test)
        self.assertEqual(r.due_date, timezone.localdate() + timedelta(days=2))

    def test_concept_incomplet_ignore(self):
        self._complete('c2', passes_done=1)   # c2 exige 2 passes
        srs.sync_reviews(self.student)
        self.assertFalse(ConceptReview.objects.filter(concept_id='c2').exists())

    def test_sync_idempotent(self):
        self._complete('c1', passes_done=1)
        srs.sync_reviews(self.student)
        srs.sync_reviews(self.student)
        self.assertEqual(
            ConceptReview.objects.filter(student=self.student, concept_id='c1').count(), 1)

    def test_contenu_regenere_reancre_ou_supprime(self):
        """Nouvelle version active : c1 survit (ré-ancré), c2 a disparu (supprimé)."""
        self._review('c1', box=3)
        self._review('c2', box=2)
        cv2 = LessonContentVersion.objects.create(
            lesson=self.lesson, version=2,
            concepts_data=[c for c in _concepts() if c['id'] == 'c1'],
        )
        self.lesson.active_content_version = cv2
        self.lesson.save(update_fields=['active_content_version'])
        srs.sync_reviews(self.student)

        r1 = ConceptReview.objects.get(student=self.student, concept_id='c1')
        self.assertEqual(r1.content_version_id, cv2.id)   # ré-ancré
        self.assertEqual(r1.box, 3)                        # progression conservée
        self.assertFalse(ConceptReview.objects.filter(concept_id='c2').exists())

    def test_concepts_data_absent_ne_plante_pas(self):
        self.lesson.active_content_version = None
        self.lesson.save(update_fields=['active_content_version'])
        srs.sync_reviews(self.student)   # ne doit lever aucune erreur
        self.assertEqual(ConceptReview.objects.count(), 0)


class ApplyResultTests(SRSBase):
    def test_reussite_monte_et_allonge(self):
        r = self._review(box=1)
        srs.apply_result(r, success=True)
        self.assertEqual(r.box, 2)
        self.assertEqual(r.due_date, timezone.localdate() + timedelta(days=7))
        self.assertIsNotNone(r.last_reviewed_at)

    def test_reussite_bornee_a_4(self):
        r = self._review(box=4)
        srs.apply_result(r, success=True)
        self.assertEqual(r.box, 4)
        self.assertEqual(r.due_date, timezone.localdate() + timedelta(days=60))

    def test_echec_descend_d_une_seule_boite(self):
        r = self._review(box=3)
        srs.apply_result(r, success=False)
        self.assertEqual(r.box, 2)

    def test_echec_borne_a_1(self):
        r = self._review(box=1)
        srs.apply_result(r, success=False)
        self.assertEqual(r.box, 1)
        self.assertEqual(r.due_date, timezone.localdate() + timedelta(days=2))


class TodayQueueTests(SRSBase):
    def test_plus_en_retard_d_abord(self):
        today = timezone.localdate()
        self._review('c1', due=today)                          # à l'heure
        self._review('c2', due=today - timedelta(days=3))      # 3 j de retard
        queue = srs.today_queue(self.student)
        self.assertEqual([i['review'].concept_id for i in queue], ['c2', 'c1'])
        self.assertEqual(queue[0]['late_days'], 3)
        self.assertEqual(queue[1]['late_days'], 0)

    def test_futur_exclu_et_cap_respecte(self):
        today = timezone.localdate()
        self._review('c1', due=today)
        self._review('c2', due=today + timedelta(days=5))      # pas encore mûr
        queue = srs.today_queue(self.student, cap=1)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['review'].concept_id, 'c1')

    def test_bonus_cours_demain_a_echeance_egale(self):
        today = timezone.localdate()
        # c1 = Français (cours demain) vs même concept d'une leçon Maths (sans cours)
        other = Lesson.objects.create(
            teacher=self.teacher, school=self.school, title='Leçon Maths',
            subject='Mathématiques', format_version=2, status=LessonStatus.READY,
        )
        cv_o = LessonContentVersion.objects.create(
            lesson=other, version=1, concepts_data=_concepts(),
        )
        other.active_content_version = cv_o
        other.save(update_fields=['active_content_version'])
        LessonDeployment.objects.create(
            lesson=other, school=self.school, school_class=self.klass,
        )
        ConceptReview.objects.create(
            student=self.student, lesson=other, content_version=cv_o,
            concept_id='c1', box=1, due_date=today,
        )
        self._review('c1', due=today)   # leçon Français

        # emploi du temps : Français DEMAIN à 8 h
        year = SchoolYear.objects.create(
            school=self.school, name='2025-2026', is_active=True,
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30),
        )
        subj = Subject.objects.create(school=self.school, name='Français')
        cs = ClassSubject.objects.create(school_class=self.klass, subject=subj)
        tomorrow = today + timedelta(days=1)
        CourseSlot.objects.create(
            class_subject=cs, school_year=year, day=tomorrow.weekday(),
            start_time='08:00', end_time='09:00',
        )

        queue = srs.today_queue(self.student)
        self.assertEqual(queue[0]['subject'], 'Français')      # boosté en tête
        self.assertIsNotNone(queue[0]['tomorrow_time'])
        self.assertIsNone(queue[1]['tomorrow_time'])

    def test_pas_d_annee_active_pas_d_erreur(self):
        self._review('c1')
        queue = srs.today_queue(self.student)     # aucun emploi du temps
        self.assertEqual(len(queue), 1)
        self.assertIsNone(queue[0]['tomorrow_time'])

    def test_isolation_autre_eleve(self):
        autre = Student.objects.create(
            school=self.school, school_class=self.klass,
            full_name='Autre Élève', tuition_fee=Decimal('0'),
        )
        ConceptReview.objects.create(
            student=autre, lesson=self.lesson, content_version=self.cv,
            concept_id='c1', box=1, due_date=timezone.localdate(),
        )
        self.assertEqual(srs.today_queue(self.student), [])
        self.assertEqual(srs.due_count(self.student), 0)


class RevisionViewsTests(SRSBase):
    """Vues /learn/revision/ — page, session, réponse (flux complet)."""

    def _login(self, student=None):
        s = self.client.session
        s['student_id'] = (student or self.student).pk
        s.save()

    def test_anonyme_redirige_vers_login(self):
        resp = self.client.get('/learn/revision/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/learn/login', resp.url)

    def test_page_affiche_la_file(self):
        self._login()
        self._review('c1', due=timezone.localdate() - timedelta(days=3))
        resp = self.client.get('/learn/revision/')
        self.assertContains(resp, 'Concept Un')
        self.assertContains(resp, '3 j de retard')
        self.assertContains(resp, "C'est parti")

    def test_page_etat_tout_est_frais(self):
        self._login()
        self._review('c1', due=timezone.localdate() + timedelta(days=1))
        resp = self.client.get('/learn/revision/')
        self.assertContains(resp, 'Tout est frais')
        self.assertContains(resp, 'Demain')      # aperçu du prochain jour
        # pas de CTA session quand rien n'est mûr
        self.assertNotContains(resp, "C'est parti")

    def test_session_sans_concept_mur_redirige(self):
        self._login()
        resp = self.client.get('/learn/revision/session/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/learn/revision/', resp.url)

    def test_flux_complet_reussite_monte_la_boite(self):
        """Session → 2 réponses justes → la boîte monte (1→2) et le bilan sort."""
        self._login()
        r = self._review('c1', box=1, due=timezone.localdate())
        resp = self.client.get('/learn/revision/session/')
        self.assertEqual(resp.status_code, 200)
        sess = self.client.session['srs_session']
        sids = list(sess['items'].keys())
        self.assertEqual(len(sids), 2)   # 2 questions tirées pour c1

        answers = {'q1': 0, 'q2': True}   # les bonnes réponses de _concepts()
        move = None
        for sid in sids:
            quiz_id = sess['items'][sid]['quiz_id']
            resp = self.client.post(
                '/learn/revision/answer/',
                {'quiz_id': sid, 'answer': answers[quiz_id]},
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['correct'])
            if data['move']:
                move = data['move']

        r.refresh_from_db()
        self.assertEqual(r.box, 2)                      # monté
        self.assertIsNotNone(move)                      # bilan renvoyé
        self.assertEqual(move['from_state'], 'fragile')
        self.assertTrue(move['up'])
        # journal marqué révision
        from .models import QuizAttempt
        self.assertEqual(QuizAttempt.objects.filter(
            student=self.student, source='revision', is_correct=True).count(), 2)

    def test_une_erreur_fait_descendre(self):
        self._login()
        r = self._review('c1', box=3, due=timezone.localdate())
        self.client.get('/learn/revision/session/')
        sess = self.client.session['srs_session']
        wrong = {'q1': 1, 'q2': False}    # tout faux
        for sid, entry in sess['items'].items():
            self.client.post('/learn/revision/answer/',
                             {'quiz_id': sid, 'answer': wrong[entry['quiz_id']]},
                             content_type='application/json')
        r.refresh_from_db()
        self.assertEqual(r.box, 2)   # 3 → 2, une seule marche

    def test_mouvement_applique_une_seule_fois(self):
        """Rejouer une réponse après complétion ne double pas le mouvement."""
        self._login()
        r = self._review('c1', box=1, due=timezone.localdate())
        self.client.get('/learn/revision/session/')
        sess = self.client.session['srs_session']
        answers = {'q1': 0, 'q2': True}
        for sid, entry in sess['items'].items():
            self.client.post('/learn/revision/answer/',
                             {'quiz_id': sid, 'answer': answers[entry['quiz_id']]},
                             content_type='application/json')
        # re-poste la 1ʳᵉ question : le concept est déjà appliqué
        sid0 = list(sess['items'].keys())[0]
        resp = self.client.post('/learn/revision/answer/',
                                {'quiz_id': sid0,
                                 'answer': answers[sess['items'][sid0]['quiz_id']]},
                                content_type='application/json')
        self.assertIsNone(resp.json()['move'])
        r.refresh_from_db()
        self.assertEqual(r.box, 2)   # toujours 2, pas 3

    def test_reponse_hors_session_rejetee(self):
        self._login()
        resp = self.client.post('/learn/revision/answer/',
                                {'quiz_id': 'r999:q1', 'answer': 0},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 409)

    def test_isolation_review_d_un_autre_eleve(self):
        """Une session forgée pointant la review d'un autre élève → 404."""
        autre = Student.objects.create(
            school=self.school, school_class=self.klass,
            full_name='Autre Élève', tuition_fee=Decimal('0'),
        )
        r_autre = ConceptReview.objects.create(
            student=autre, lesson=self.lesson, content_version=self.cv,
            concept_id='c1', box=1, due_date=timezone.localdate(),
        )
        self._login()
        s = self.client.session
        s['srs_session'] = {'items': {f'r{r_autre.id}:q1': {
            'review_id': r_autre.id, 'quiz_id': 'q1', 'correct': None}}, 'applied': []}
        s.save()
        resp = self.client.post('/learn/revision/answer/',
                                {'quiz_id': f'r{r_autre.id}:q1', 'answer': 0},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 404)


class DashboardsTests(SRSBase):
    def test_garden_counts(self):
        self._review('c1', box=1)
        self._review('c2', box=3)
        counts = srs.garden_counts(self.student)
        self.assertEqual(counts, {'fragile': 1, 'solide': 1, 'maitrise': 0})

    def test_next_days_preview_groupe_par_date(self):
        today = timezone.localdate()
        self._review('c1', due=today + timedelta(days=1))
        self._review('c2', due=today + timedelta(days=1))
        preview = srs.next_days_preview(self.student)
        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]['count'], 2)
        self.assertEqual(preview[0]['date'], today + timedelta(days=1))
        self.assertIn('Français', preview[0]['subjects'])

    def test_due_count(self):
        today = timezone.localdate()
        self._review('c1', due=today - timedelta(days=1))
        self._review('c2', due=today + timedelta(days=9))
        self.assertEqual(srs.due_count(self.student), 1)
