"""
Tests du rate-limiting de la connexion (protection anti-force-brute).

Couvre : connexion normale OK, verrou après 5 échecs, et surtout le verrou
*par compte* qui tient même quand l'IP change (défense contre une attaque
distribuée sur un seul numéro). Ce dernier s'appuie sur le cache partagé
(DatabaseCache) — d'où l'exécution avec un vrai backend de cache.

Lancer : venv/bin/python manage.py test apps.accounts
"""
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache

from apps.accounts.models import User, UserRole


class LoginRateLimitTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            phone_number='70000001', password='bon-mot-de-passe',
            role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.url = reverse('accounts:login')

    def setUp(self):
        cache.clear()   # repart d'un compteur vierge (ceinture + bretelles)

    def _try(self, password, ip='10.0.0.1'):
        return self.client.post(
            self.url, {'phone_number': '70000001', 'password': password},
            HTTP_X_FORWARDED_FOR=ip,
        )

    def test_connexion_reussie(self):
        # Le bon mot de passe connecte (prouve aussi que le champ posté est bien phone_number).
        self._try('bon-mot-de-passe')
        self.assertIn('_auth_user_id', self.client.session)

    def test_verrou_apres_5_echecs(self):
        for _ in range(5):
            self._try('faux')
        # 6e essai avec le BON mot de passe → refusé car verrouillé, pas de session.
        r = self._try('bon-mot-de-passe')
        self.assertTrue(r.context['locked'])
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verrou_par_compte_meme_si_ip_change(self):
        # 5 échecs sur le même compte depuis 5 IP différentes → le compte est verrouillé.
        # (Sans la clé « par téléphone », aucune IP n'atteindrait 5 → pas de verrou.)
        for i in range(5):
            self._try('faux', ip=f'10.0.0.{i}')
        r = self._try('bon-mot-de-passe', ip='10.0.0.99')
        self.assertTrue(r.context['locked'])
        self.assertNotIn('_auth_user_id', self.client.session)


class ForcePasswordChangeTests(TestCase):
    """Le mot de passe temporaire posé par l'école DOIT mourir après un seul usage :
    tant que must_change_password est vrai, tout est bloqué sauf la page de choix."""

    def setUp(self):
        from django.urls import reverse
        self.parent = User.objects.create_user(
            phone_number='70000099', password='TEMP1234',
            full_name='Parent Force', role=UserRole.PARENT, must_change_password=True,
        )
        self.set_url = reverse('accounts:password-set')
        self.client.force_login(self.parent)

    def test_flag_bloque_toute_page(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 302)
        self.assertIn(self.set_url, r.headers['Location'])

    def test_page_de_choix_ne_boucle_pas(self):
        # La page de choix elle-même doit répondre 200 (sinon redirection infinie).
        self.assertEqual(self.client.get(self.set_url).status_code, 200)

    def test_mdp_trop_court_refuse(self):
        self.client.post(self.set_url, {'password': '12', 'confirm': '12'})
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.must_change_password)          # inchangé

    def test_confirmation_differente_refuse(self):
        self.client.post(self.set_url, {'password': 'abcd', 'confirm': 'abce'})
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.must_change_password)

    def test_choix_valide_libere_et_tue_le_temporaire(self):
        from django.contrib.auth import authenticate
        self.client.post(self.set_url, {'password': 'monsecret', 'confirm': 'monsecret'})
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.must_change_password)         # libéré
        self.assertIsNotNone(authenticate(phone_number='70000099', password='monsecret'))  # nouveau OK
        self.assertIsNone(authenticate(phone_number='70000099', password='TEMP1234'))      # temporaire mort
        # plus de redirection après le changement
        self.assertNotIn(self.set_url, self.client.get('/dashboard/').headers.get('Location', ''))


class TeamPasswordLifecycleTests(TestCase):
    """Niveau 1 (intérimaire, avant auth e-mail) : le mot de passe d'un membre d'équipe
    posé par l'école est temporaire à usage unique, et régénérable par le directeur."""

    def setUp(self):
        from apps.schools.models import School
        from apps.accounts.models import Membership
        self.school = School.objects.create(
            name='École RH', short_name='RH', city='Bamako', school_type='primary',
        )
        self.director = User.objects.create_user(
            phone_number='70001000', password='pw', full_name='Directrice',
            role=UserRole.DIRECTOR,
        )
        Membership.objects.create(user=self.director, school=self.school,
                                  role=UserRole.DIRECTOR, is_active=True)
        self.teacher = User.objects.create_user(
            phone_number='70001001', password='ancien-mdp', full_name='Prof X',
            role=UserRole.TEACHER, must_change_password=False,
        )
        Membership.objects.create(user=self.teacher, school=self.school,
                                  role=UserRole.TEACHER, is_active=True)
        # session multi-école : poser l'école active
        self.client.force_login(self.director)
        s = self.client.session
        s['active_school_id'] = self.school.id
        s.save()

    def test_regeneration_change_le_mdp_arme_le_forcage(self):
        import json
        from django.contrib.auth import authenticate
        from django.urls import reverse
        r = self.client.post(reverse('team:regenerate-password', args=[self.teacher.id]))
        self.assertEqual(r.status_code, 200)
        creds = json.loads(r['HX-Trigger'])['staffCredentials']
        new_pwd = creds['temp_pwd']
        self.assertEqual(creds['phone'], '70001001')
        self.teacher.refresh_from_db()
        # nouveau marche, ancien mort, changement forcé armé
        self.assertIsNotNone(authenticate(phone_number='70001001', password=new_pwd))
        self.assertIsNone(authenticate(phone_number='70001001', password='ancien-mdp'))
        self.assertTrue(self.teacher.must_change_password)

    def test_regeneration_reservee_au_directeur(self):
        from django.urls import reverse
        from apps.accounts.models import Membership
        # un prof (pas directeur) ne peut PAS régénérer
        self.client.force_login(self.teacher)
        s = self.client.session; s['active_school_id'] = self.school.id; s.save()
        r = self.client.post(reverse('team:regenerate-password', args=[self.director.id]))
        self.assertIn(r.status_code, (302, 403))               # refusé (jamais 200)
        self.director.refresh_from_db()
        self.assertFalse(self.director.must_change_password)   # mdp du directeur intact


class TeamSubjectsLazyLoadTests(TestCase):
    """#12 — la section « Matières » d'une fiche staff (lazy) ne doit PAS renvoyer
    un 404 muet (→ « Chargement… » figé) pour un directeur qui enseigne aussi.
    L'endpoint accepte tout membre de l'école, pas seulement User.role=TEACHER."""

    def setUp(self):
        from apps.schools.models import School
        from apps.accounts.models import Membership
        # École A = l'école PRINCIPALE (User.school) de la personne
        self.autre_ecole = School.objects.create(
            name='A', short_name='A', city='Bamako', school_type='primary')
        # École B = celle qu'on regarde, où la personne est ENSEIGNANTE
        self.school = School.objects.create(
            name='B', short_name='B', city='Bamako', school_type='primary',
            accounting_enabled=True)
        self.director = User.objects.create_user(
            phone_number='70002000', password='pw', full_name='Dir B',
            role=UserRole.DIRECTOR, school=self.school, must_change_password=False)
        Membership.objects.create(user=self.director, school=self.school,
                                  role=UserRole.DIRECTOR, is_active=True)
        # Sory : directeur GLOBAL (User.school = école A), mais ENSEIGNANT dans B
        self.multi = User.objects.create_user(
            phone_number='70002001', password='pw', full_name='Multi',
            role=UserRole.DIRECTOR, school=self.autre_ecole, must_change_password=False)
        Membership.objects.create(user=self.multi, school=self.autre_ecole,
                                  role=UserRole.DIRECTOR, is_active=True)
        Membership.objects.create(user=self.multi, school=self.school,
                                  role=UserRole.TEACHER, is_active=True)
        self.client.force_login(self.director)
        s = self.client.session
        s['active_school_id'] = self.school.id
        s.save()

    def test_sections_lazy_membre_multi_ecole_ne_404_pas(self):
        from django.urls import reverse
        # AVANT le fix : filtre User.school → l'école principale (A) ≠ B → 404 →
        # « Chargement… » figé pour les matières ET la rémunération.
        for url in [reverse('team:subjects', args=[self.multi.id]),
                    reverse('accounting:staff-remuneration', args=[self.multi.id])]:
            resp = self.client.get(url, HTTP_HX_REQUEST='true')
            self.assertEqual(resp.status_code, 200, url)
