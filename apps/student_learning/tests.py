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
    Bulletin, BulletinLine, ClassSubject, CourseSlot, FormativeEvaluation,
    FormativeGrade, Note, NoteType, Period, School, SchoolClass, SchoolYear,
    Subject,
)
from apps.students.models import Student

from . import srs, cahier
from .models import ConceptProgress, ConceptReview, CahierAttempt

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


class MasteryBySubjectTests(SRSBase):
    def test_groupe_par_matiere_et_compte_fragiles(self):
        # 2 concepts Français dans self.lesson (boîtes 1 et 3)
        self._review('c1', box=1)
        self._review('c2', box=3)
        rows, total_fragile = srs.mastery_by_subject(self.student)
        self.assertEqual(rows['Français'],
                         {'fragile': 1, 'solide': 1, 'maitrise': 0, 'total': 2})
        self.assertEqual(total_fragile, 1)

    def test_deux_matieres_distinctes(self):
        other = Lesson.objects.create(
            teacher=self.teacher, school=self.school, title='Leçon Maths',
            subject='Mathématiques', format_version=2, status=LessonStatus.READY,
        )
        cv_o = LessonContentVersion.objects.create(
            lesson=other, version=1, concepts_data=_concepts(),
        )
        self._review('c1', box=1)
        ConceptReview.objects.create(
            student=self.student, lesson=other, content_version=cv_o,
            concept_id='c1', box=4, due_date=timezone.localdate(),
        )
        rows, total_fragile = srs.mastery_by_subject(self.student)
        self.assertEqual(rows['Français']['fragile'], 1)
        self.assertEqual(rows['Mathématiques']['maitrise'], 1)
        self.assertEqual(total_fragile, 1)

    def test_vide_si_aucune_revision(self):
        rows, total_fragile = srs.mastery_by_subject(self.student)
        self.assertEqual(rows, {})
        self.assertEqual(total_fragile, 0)


class ProgressContextTests(SRSBase):
    """student_progress_context — les 3 couches école, chacune optionnelle."""

    def _year_period(self, notes_open=True):
        year = SchoolYear.objects.create(
            school=self.school, name='2025-2026', is_active=True,
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30),
        )
        period = Period.objects.create(
            school_year=year, school_class=self.klass, name='Trimestre 1',
            order=1, is_notes_open=notes_open,
        )
        return year, period

    def _class_subject(self, name='Français', max_grade=Decimal('20')):
        subj = Subject.objects.create(school=self.school, name=name)
        return ClassSubject.objects.create(
            school_class=self.klass, subject=subj, max_grade=max_grade)

    def test_ecole_silencieuse_tout_none(self):
        from apps.student_learning.views import student_progress_context
        self._year_period()
        ctx = student_progress_context(self.student)
        self.assertFalse(ctx['has_school'])
        self.assertIsNone(ctx['bulletin'])
        self.assertEqual(ctx['subject_rows'], [])
        self.assertEqual(ctx['evals'], [])

    def test_pas_d_annee_ne_plante_pas(self):
        from apps.student_learning.views import student_progress_context
        ctx = student_progress_context(self.student)   # aucune année active
        self.assertFalse(ctx['has_school'])

    def test_bulletin_publie_officiel(self):
        from apps.student_learning.views import student_progress_context
        year, period = self._year_period()
        cs = self._class_subject('Français', Decimal('20'))
        bul = Bulletin.objects.create(
            student=self.student, period=period, school_class=self.klass,
            is_published=True, general_average=Decimal('14.50'),
            rank=5, class_size=42, first_average=Decimal('16.20'),
            appreciation='Bon trimestre', generated_by=self.teacher,
        )
        BulletinLine.objects.create(
            bulletin=bul, class_subject=cs, final_average=Decimal('15.50'),
            rank_in_subject=2, appreciation='Très bien',
        )
        ctx = student_progress_context(self.student)
        self.assertTrue(ctx['has_school'])
        self.assertFalse(ctx['is_provisional'])
        self.assertEqual(ctx['bulletin']['average'], Decimal('14.50'))
        self.assertEqual(ctx['bulletin']['rank'], 5)
        self.assertEqual(ctx['bulletin']['max'], Decimal('20'))
        self.assertIn('/learn/grades/bulletin/', ctx['bulletin']['pdf_url'])
        self.assertEqual(len(ctx['subject_rows']), 1)
        self.assertEqual(ctx['subject_rows'][0]['average'], Decimal('15.50'))

    def test_bulletin_non_publie_bascule_en_provisoire(self):
        from apps.student_learning.views import student_progress_context
        year, period = self._year_period()
        cs = self._class_subject('Mathématiques', Decimal('10'))
        # bulletin existe mais PAS publié → ignoré
        Bulletin.objects.create(
            student=self.student, period=period, school_class=self.klass,
            is_published=False, general_average=Decimal('8'),
            generated_by=self.teacher,
        )
        Note.objects.create(
            student=self.student, class_subject=cs, period=period,
            note_type=NoteType.DEVOIR, position=1, value=Decimal('7'),
            entered_by=self.teacher,
        )
        Note.objects.create(
            student=self.student, class_subject=cs, period=period,
            note_type=NoteType.COMPOSITION, position=2, value=Decimal('9'),
            entered_by=self.teacher,
        )
        ctx = student_progress_context(self.student)
        self.assertTrue(ctx['is_provisional'])
        self.assertIsNone(ctx['bulletin'])
        self.assertEqual(len(ctx['subject_rows']), 1)
        self.assertEqual(ctx['subject_rows'][0]['average'], Decimal('8'))  # (7+9)/2
        self.assertEqual(ctx['subject_rows'][0]['max'], Decimal('10'))     # barème réel
        self.assertEqual(ctx['provisional_avg'], Decimal('8'))

    def test_evaluations_publiees_seulement(self):
        from apps.student_learning.views import student_progress_context
        year, period = self._year_period()
        cs = self._class_subject('Français')
        ev_pub = FormativeEvaluation.objects.create(
            class_subject=cs, period=period, date=date(2026, 7, 8),
            title='Dictée', max_grade=Decimal('20'), is_published_to_parent=True,
        )
        ev_priv = FormativeEvaluation.objects.create(
            class_subject=cs, period=period, date=date(2026, 7, 9),
            title='Interro secrète', max_grade=Decimal('20'),
            is_published_to_parent=False,
        )
        FormativeGrade.objects.create(evaluation=ev_pub, student=self.student, value=Decimal('16'))
        FormativeGrade.objects.create(evaluation=ev_priv, student=self.student, value=Decimal('4'))
        ctx = student_progress_context(self.student)
        self.assertEqual(len(ctx['evals']), 1)          # seule la publiée
        self.assertEqual(ctx['evals'][0]['title'], 'Dictée')
        self.assertEqual(ctx['evals'][0]['value'], Decimal('16'))

    def test_isolation_autre_eleve(self):
        from apps.student_learning.views import student_progress_context
        year, period = self._year_period()
        cs = self._class_subject('Français')
        autre = Student.objects.create(
            school=self.school, school_class=self.klass,
            full_name='Autre Élève', tuition_fee=Decimal('0'),
        )
        bul = Bulletin.objects.create(
            student=autre, period=period, school_class=self.klass,
            is_published=True, general_average=Decimal('18'),
            generated_by=self.teacher,
        )
        ctx = student_progress_context(self.student)
        self.assertIsNone(ctx['bulletin'])   # le bulletin de l'autre n'apparaît pas


class ProgresViewTests(ProgressContextTests):
    """Vue /learn/progres/ — rendu des 3 états + sécurité."""

    def _login(self, student=None):
        s = self.client.session
        s['student_id'] = (student or self.student).pk
        s.save()

    def test_anonyme_redirige_vers_login(self):
        resp = self.client.get('/learn/progres/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/learn/login', resp.url)

    def test_ecole_silencieuse_app_d_abord(self):
        # de la maîtrise mais aucune note école
        self._year_period()
        self._review('c1', box=1)
        self._login()
        resp = self.client.get('/learn/progres/')
        self.assertContains(resp, 'Dans l\'app')
        self.assertContains(resp, "Tes notes d'école apparaîtront ici")
        self.assertNotContains(resp, 'Moyenne provisoire')

    def test_bulletin_publie_rendu_avec_pdf(self):
        year, period = self._year_period()
        cs = self._class_subject('Français', Decimal('20'))
        bul = Bulletin.objects.create(
            student=self.student, period=period, school_class=self.klass,
            is_published=True, general_average=Decimal('14.50'),
            rank=5, class_size=42, appreciation='Bon trimestre',
            generated_by=self.teacher,
        )
        BulletinLine.objects.create(
            bulletin=bul, class_subject=cs, final_average=Decimal('15.50'),
            rank_in_subject=2,
        )
        self._login()
        resp = self.client.get('/learn/progres/')
        self.assertContains(resp, 'Voir mon bulletin (PDF)')
        self.assertContains(resp, '14,50')                 # localize off → virgule FR
        self.assertContains(resp, '/learn/grades/bulletin/')
        self.assertNotContains(resp, 'Moyenne provisoire')

    def test_provisoire_rendu_avec_etiquette(self):
        year, period = self._year_period()
        cs = self._class_subject('Mathématiques', Decimal('20'))
        Note.objects.create(
            student=self.student, class_subject=cs, period=period,
            note_type=NoteType.DEVOIR, position=1, value=Decimal('12'),
            entered_by=self.teacher,
        )
        self._login()
        resp = self.client.get('/learn/progres/')
        self.assertContains(resp, 'Provisoire')
        self.assertContains(resp, 'Moyenne provisoire')
        self.assertNotContains(resp, 'Voir mon bulletin (PDF)')

    def test_page_tout_vide_invite_a_commencer(self):
        self._year_period()
        self._login()   # ni notes ni révision
        resp = self.client.get('/learn/progres/')
        self.assertContains(resp, 'Ta page de progrès est prête')

    def test_cta_reviser_montre_le_vrai_compte(self):
        self._year_period()
        self._review('c1', box=1)
        self._review('c2', box=1)
        self._login()
        resp = self.client.get('/learn/progres/')
        self.assertContains(resp, 'Réviser mes 2 concepts fragiles')

    def test_pdf_d_un_autre_eleve_404(self):
        year, period = self._year_period()
        autre = Student.objects.create(
            school=self.school, school_class=self.klass,
            full_name='Autre Élève', tuition_fee=Decimal('0'),
        )
        bul = Bulletin.objects.create(
            student=autre, period=period, school_class=self.klass,
            is_published=True, general_average=Decimal('18'),
            generated_by=self.teacher,
        )
        self._login()   # connecté en self.student
        resp = self.client.get(f'/learn/grades/bulletin/{bul.pk}/pdf/')
        self.assertEqual(resp.status_code, 404)


def _reading(with_terms=True):
    """reading_data réaliste : sections avec text + simple, glossaire."""
    r = {
        'title': 'Le corps humain',
        'direction': 'ltr',
        'sections': [
            {'id': 's1', 'title': 'Introduction', 'blocks': [
                {'type': 'p',
                 'text': "Chaque matin tu te lèves et tu entends les bruits du quartier autour de toi. "
                         "Tout cela, c'est grâce à ton corps qui travaille sans arrêt.",
                 'simple': "Ton corps t'aide à faire tes activités du matin au soir. Il travaille pour toi."},
            ]},
        ],
    }
    if with_terms:
        r['terms'] = {'sens': "La capacité du corps à percevoir le monde autour de toi."}
    return r


class CahierDeriveTests(SRSBase):
    """Dérivation Voie B enrichie — matrice NIVEAU × MATIÈRE."""

    def _cv_with(self, level='fondamental_1', subject='Français', subject_type='literary',
                 reading=None, concepts=None):
        self.lesson.level = level
        self.lesson.subject = subject
        self.lesson.subject_type = subject_type
        self.lesson.save(update_fields=['level', 'subject', 'subject_type'])
        self.cv.reading_data = _reading() if reading is None else reading
        if concepts is not None:
            self.cv.concepts_data = concepts
        self.cv.save(update_fields=['reading_data', 'concepts_data'])
        return self.cv

    # ── Dictée : langue + bas/moyen niveau seulement ──
    def test_langue_bas_niveau_prep_serie_dictee_copie(self):
        cv = self._cv_with('fondamental_1', 'Français', 'literary')
        tasks = cahier.derive_cahier_tasks(cv, self.lesson)
        kinds = [t['kind'] for t in tasks]
        self.assertEqual(kinds[0], 'prep')                 # préparation d'abord
        self.assertGreaterEqual(kinds.count('dictee'), 2)  # SÉRIE (pas une seule)
        self.assertEqual(kinds[-1], 'copie')               # copie en complément
        self.assertTrue(tasks[0]['words'])                 # mots à préparer

    def test_subject_type_incoherent_lang_reconnu(self):
        # donnée réelle incohérente : subject_type='lang' → doit rester une langue
        cv = self._cv_with('fondamental_1', 'Français', 'lang')
        kinds = [t['kind'] for t in cahier.derive_cahier_tasks(cv, self.lesson)]
        self.assertIn('dictee', kinds)

    def test_matiere_non_langue_jeune_aucun_noeud(self):
        # maths fond.1 : pas de dictée (pas une langue), pas de compo (trop tôt) → RIEN
        cv = self._cv_with('fondamental_1', 'Mathématiques', 'math')
        self.assertEqual(cahier.derive_cahier_tasks(cv, self.lesson), [])
        self.assertFalse(cahier.has_cahier(cv, self.lesson))

    def test_pas_de_dictee_au_lycee_meme_en_langue(self):
        cv = self._cv_with('secondaire_gen', 'Français', 'literary')
        kinds = [t['kind'] for t in cahier.derive_cahier_tasks(cv, self.lesson)]
        self.assertNotIn('dictee', kinds)
        self.assertIn('production', kinds)

    # ── Compositions : plusieurs, forme par matière ──
    def test_compositions_multiples_forme_maths(self):
        cv = self._cv_with('secondaire_gen', 'Mathématiques', 'math')
        prods = [t for t in cahier.derive_cahier_tasks(cv, self.lesson)
                 if t['kind'] == 'production']
        self.assertGreaterEqual(len(prods), 2)             # PLUSIEURS
        self.assertIn('rédige toute ta démarche', prods[0]['prompt'])   # forme maths

    def test_composition_forme_lettres(self):
        cv = self._cv_with('secondaire_gen', 'Français', 'literary')
        prod = next(t for t in cahier.derive_cahier_tasks(cv, self.lesson)
                    if t['kind'] == 'production')
        self.assertIn('Rédige un court texte', prod['prompt'])

    def test_forme_maths_par_le_nom_malgre_type_other(self):
        # subject_type='other' mais nom='Mathématiques' → forme maths (robustesse)
        cv = self._cv_with('secondaire_gen', 'Mathématiques', 'other')
        prod = next(t for t in cahier.derive_cahier_tasks(cv, self.lesson)
                    if t['kind'] == 'production')
        self.assertIn('démarche', prod['prompt'])

    def test_fond2_langue_dictee_plus_une_compo(self):
        # fondamental 2 langue : dictée (cœur) + UNE seule compo (ne pas noyer)
        cv = self._cv_with('fondamental_2', 'Français', 'literary')
        kinds = [t['kind'] for t in cahier.derive_cahier_tasks(cv, self.lesson)]
        self.assertIn('dictee', kinds)
        self.assertEqual(kinds.count('production'), 1)

    # ── Défensif ──
    def test_sans_contenu_aucun_noeud(self):
        cv = self._cv_with('fondamental_1', reading={}, concepts=[])
        self.assertEqual(cahier.derive_cahier_tasks(cv, self.lesson), [])

    def test_reading_malforme_ne_plante_pas(self):
        cv = self._cv_with('fondamental_1', 'Mathématiques', 'math',
                            reading={'sections': [None, {'blocks': [None, 'x']}]})
        self.assertEqual(cahier.derive_cahier_tasks(cv, self.lesson), [])

    def test_deterministe(self):
        cv = self._cv_with('fondamental_1', 'Français', 'literary')
        a = cahier.derive_cahier_tasks(cv, self.lesson)
        b = cahier.derive_cahier_tasks(cv, self.lesson)
        self.assertEqual([t.get('text') for t in a], [t.get('text') for t in b])


class CahierViewTests(SRSBase):
    """Vues /learn/v2/lesson/<id>/cahier/ + nœud non-bloquant dans assemble_nodes."""

    def _login(self, student=None):
        s = self.client.session
        s['student_id'] = (student or self.student).pk
        s.save()

    def _with_reading(self):
        self.cv.reading_data = _reading()
        self.cv.save(update_fields=['reading_data'])

    def _url(self, suffix=''):
        return f'/learn/v2/lesson/{self.lesson.id}/cahier/{suffix}'

    def test_anonyme_redirige_vers_login(self):
        self._with_reading()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/learn/login', resp.url)

    def test_runner_affiche_les_taches(self):
        self._with_reading()
        self._login()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'sur papier')
        self.assertContains(resp, 'cahier-tasks')      # json_script des tâches

    def test_404_si_aucune_tache_derivable(self):
        self.cv.reading_data = {}
        self.cv.concepts_data = []
        self.cv.save(update_fields=['reading_data', 'concepts_data'])
        self._login()
        self.assertEqual(self.client.get(self._url()).status_code, 404)

    def test_finish_persiste_l_auto_evaluation(self):
        self._with_reading()
        self._login()
        resp = self.client.post(
            self._url('finish/'),
            {'results': [{'task_id': 'dictee', 'self': 'good'},
                         {'task_id': 'copie', 'self': 'partial'}]},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['first_time'])
        att = CahierAttempt.objects.get(student=self.student, content_version=self.cv)
        self.assertEqual(len(att.results), 2)
        self.assertEqual(att.results[0], {'task_id': 'dictee', 'self': 'good'})

    def test_finish_nettoie_les_resultats_invalides(self):
        self._with_reading()
        self._login()
        resp = self.client.post(
            self._url('finish/'),
            {'results': [{'task_id': 'dictee', 'self': 'good'},
                         {'task_id': 'x', 'self': 'triche'},   # self invalide → rejeté
                         'pas-un-dict']},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        att = CahierAttempt.objects.get(student=self.student, content_version=self.cv)
        self.assertEqual(len(att.results), 1)   # seul le valide est gardé

    def test_isolation_autre_classe_404(self):
        self._with_reading()
        autre_ecole = School.objects.create(
            name='Autre', short_name='AU', city='Bamako', school_type='primary')
        autre_classe = SchoolClass.objects.create(
            school=autre_ecole, name='1B', level='fondamental_1',
            annual_fee=Decimal('0'), max_capacity=40)
        etr = Student.objects.create(
            school=autre_ecole, school_class=autre_classe,
            full_name='Étranger', tuition_fee=Decimal('0'))
        self._login(etr)   # leçon PAS déployée dans sa classe
        self.assertEqual(self.client.get(self._url()).status_code, 404)

    # ── nœud non-bloquant dans le parcours ──
    def _all_quizzes_done(self):
        self._complete('c1', passes_done=1)
        self._complete('c2', passes_done=2)

    def test_noeud_cahier_bloque_tant_que_quiz_non_finis(self):
        from apps.student_learning.views import assemble_nodes
        self._with_reading()
        self.cv.story_data = {'scene': {'name': 'S'}, 'characters': [{}], 'steps': [{}]}
        self.cv.save(update_fields=['story_data'])
        nodes = assemble_nodes(self.cv, self.student)
        cah = next(n for n in nodes if n['type'] == 'cahier')
        self.assertEqual(cah['status'], 'locked')   # quiz pas finis

    def test_noeud_cahier_available_et_ne_bloque_pas_la_suite(self):
        from apps.student_learning.views import assemble_nodes
        self._with_reading()
        self.cv.story_data = {'scene': {'name': 'S'}, 'characters': [{}], 'steps': [{}]}
        self.cv.exam_data = {'questions': [{}]}
        self.cv.save(update_fields=['story_data', 'exam_data'])
        self._all_quizzes_done()
        nodes = assemble_nodes(self.cv, self.student)
        cah = next(n for n in nodes if n['type'] == 'cahier')
        story = next(n for n in nodes if n['type'] == 'story')
        # cahier = ouvert (available), mais NON fait...
        self.assertEqual(cah['status'], 'available')
        # ...et pourtant l'histoire APRÈS lui est jouable (current), pas verrouillée.
        self.assertEqual(story['status'], 'current')
