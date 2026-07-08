"""
Tests des chemins financiers critiques (l'argent — zéro erreur tolérée).

Couvre : génération des frais à l'inscription, découpage exact de la scolarité en
tranches (jamais un franc perdu), tenue automatique par genre, et l'allocation des
paiements (FIFO, jamais de sur-allocation, jamais entre familles de dettes).

Lancer : venv/bin/python manage.py test apps.finance
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User, UserRole
from apps.schools.models import School, SchoolYear, SchoolClass
from apps.students.models import Student, StudentEnrollment, EnrollmentStatus
from apps.finance.models import (
    FeeType, FeeVariant, FeeCategory, AppliesTo, FeeDebtKind, PaymentScheduleTemplate,
)
from apps.finance.services import (
    build_fee_account, allocate_payment, student_fee_summary, fee_accounts_annotated,
)
from apps.payments.models import Payment


class FinanceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.director = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('244000'), max_capacity=40,
        )
        # Élève FILLE (pour tester la tenue auto par genre).
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, full_name='Awa Traore',
            gender='F', tuition_fee=Decimal('244000'),
        )
        cls.enrollment = StudentEnrollment.objects.create(
            student=cls.student, school=cls.school, school_class=cls.klass,
            school_year=cls.year, status=EnrollmentStatus.ACTIVE,
        )

        # Catalogue : Inscription (simple, obligatoire) + Tenue (à variantes par genre).
        cls.inscription_fee = FeeType.objects.create(
            school=cls.school, name='Inscription', category=FeeCategory.ONE_TIME,
            default_amount=Decimal('15000'), is_mandatory=True, applies_to=AppliesTo.ALL,
        )
        cls.tenue_fee = FeeType.objects.create(
            school=cls.school, name='Tenue', category=FeeCategory.ONE_TIME,
            is_mandatory=True, has_variants=True, is_gender_based=True, applies_to=AppliesTo.ALL,
        )
        FeeVariant.objects.create(fee_type=cls.tenue_fee, label='Fille', amount=Decimal('6000'), gender_key='F')
        FeeVariant.objects.create(fee_type=cls.tenue_fee, label='Garçon', amount=Decimal('5000'), gender_key='M')

        # Génère la fiche (scolarité + obligatoires). Gabarit Trimestriel (3) auto-provisionné.
        cls.account = build_fee_account(cls.enrollment)

    def _tuition(self):
        return self.account.debts.get(kind=FeeDebtKind.TUITION)

    def _pay(self, amount):
        return Payment.objects.create(
            student=self.student, amount=Decimal(amount), payment_date=date.today(),
            payment_method='cash', collected_by=self.director,
        )

    # ── Génération + découpage ─────────────────────────────────
    def test_scolarite_decoupee_sans_perte_de_franc(self):
        installs = list(self._tuition().installments.order_by('sequence'))
        amounts = [i.amount_due for i in installs]
        self.assertEqual(len(installs), 3)                                  # gabarit Trimestriel
        self.assertEqual(amounts, [Decimal('81334'), Decimal('81333'), Decimal('81333')])
        self.assertEqual(sum(amounts), Decimal('244000'))                   # somme EXACTE

    def test_tenue_auto_selon_le_genre(self):
        # Élève fille → tenue = variante Fille (6000), pas Garçon (5000).
        tenue_debt = self.account.debts.get(fee_type=self.tenue_fee)
        self.assertEqual(tenue_debt.total_amount, Decimal('6000'))

    def test_inscription_obligatoire_generee(self):
        insc = self.account.debts.get(fee_type=self.inscription_fee)
        self.assertEqual(insc.total_amount, Decimal('15000'))

    # ── Allocation ─────────────────────────────────────────────
    def test_allocation_fifo(self):
        # 50 000 sur la scolarité → remplit la tranche 1 d'abord.
        allocate_payment(self._pay('50000'), self._tuition())
        t1, t2, _ = self._tuition().installments.order_by('sequence')
        self.assertEqual(t1.amount_allocated(), Decimal('50000'))
        self.assertEqual(t1.balance(), Decimal('31334'))    # 81334 - 50000
        self.assertEqual(t2.amount_allocated(), Decimal('0'))  # tranche 2 intacte

    def test_jamais_de_sur_allocation(self):
        # Payer 300 000 sur une scolarité de 244 000 → n'alloue que 244 000.
        allocate_payment(self._pay('300000'), self._tuition())
        total = sum(i.amount_allocated() for i in self._tuition().installments.all())
        self.assertEqual(total, Decimal('244000'))

    def test_jamais_entre_familles(self):
        # Payer la scolarité ne doit JAMAIS toucher l'inscription.
        allocate_payment(self._pay('50000'), self._tuition())
        insc = self.account.debts.get(fee_type=self.inscription_fee)
        self.assertEqual(insc.installments.first().amount_allocated(), Decimal('0'))


class SoldeCoherenceTests(TestCase):
    """Cohérence du solde : la source unique (student_fee_summary / fee_accounts_annotated)
    consommée par l'admin, le parent ET le promoteur donne le MÊME chiffre correct."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École Test', short_name='ET', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.director = User.objects.create_user(
            phone_number='70000001', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('244000'), max_capacity=40,
        )
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, full_name='Awa Traore',
            gender='F', tuition_fee=Decimal('244000'),
        )
        enr = StudentEnrollment.objects.create(
            student=cls.student, school=cls.school, school_class=cls.klass,
            school_year=cls.year, status=EnrollmentStatus.ACTIVE,
        )
        cls.account = build_fee_account(enr)   # scolarité 244000 seule (pas de catalogue)

    def _pay_partial(self, amount):
        tuition = self.account.debts.get(kind=FeeDebtKind.TUITION)
        p = Payment.objects.create(
            student=self.student, amount=Decimal(amount), payment_date=date.today(),
            payment_method='cash', collected_by=self.director,
        )
        allocate_payment(p, tuition)

    def test_solde_correct_apres_paiement(self):
        self._pay_partial('100000')
        s = student_fee_summary(self.student)
        self.assertEqual(s['due'], Decimal('244000'))
        self.assertEqual(s['paid'], Decimal('100000'))
        self.assertEqual(s['balance'], Decimal('144000'))
        self.assertEqual(s['status'], 'partial')

    def test_agregat_promoteur_coherent(self):
        # Le total dû/versé (fee_accounts_annotated, base du dashboard/promoteur) = le solde élève.
        self._pay_partial('100000')
        accounts = list(fee_accounts_annotated(school=self.school))
        self.assertEqual(sum(a.due for a in accounts), Decimal('244000'))
        self.assertEqual(sum(a.paid for a in accounts), Decimal('100000'))


class DiscountTests(TestCase):
    """Remises (FeeAdjustment) — l'argent, zéro erreur tolérée. % et montant fixe,
    garde-fou anti trop-perçu, remise après paiement, annulation, gratuité totale."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École D', short_name='ED', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.director = User.objects.create_user(
            phone_number='70000050', password='pw', role=UserRole.DIRECTOR, full_name='Dir',
        )
        cls.klass = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('240000'), max_capacity=40,
        )
        cls.student = Student.objects.create(
            school=cls.school, school_class=cls.klass, first_name='Awa', last_name='Traoré',
            gender='F', tuition_fee=Decimal('240000'),
        )
        enr = StudentEnrollment.objects.create(
            student=cls.student, school=cls.school, school_class=cls.klass,
            school_year=cls.year, status=EnrollmentStatus.ACTIVE,
        )
        cls.account = build_fee_account(enr)

    def _tuition(self):
        return self.account.debts.get(kind=FeeDebtKind.TUITION)

    def _pay(self, amount):
        p = Payment.objects.create(
            student=self.student, amount=Decimal(amount), payment_date=date.today(),
            payment_method='cash', collected_by=self.director,
        )
        allocate_payment(p, self._tuition())
        return p

    def test_remise_pourcentage_reduit_solde(self):
        from apps.finance.services import create_fee_discount
        t = self._tuition()
        create_fee_discount(t, motif='fratrie', percent=10)
        self.assertEqual(t.adjustments_total(), Decimal('24000'))
        self.assertEqual(t.net_due(), Decimal('216000'))     # snapshot 240000 intact
        self.assertEqual(t.balance(), Decimal('216000'))

    def test_remise_montant_fixe(self):
        from apps.finance.services import create_fee_discount
        t = self._tuition()
        adj = create_fee_discount(t, motif='gesture', amount=25000)
        self.assertEqual(adj.resolved_amount, Decimal('25000'))
        self.assertEqual(t.balance(), Decimal('215000'))

    def test_remise_apres_paiement_partiel(self):
        from apps.finance.services import create_fee_discount
        self._pay('100000')
        t = self._tuition()
        create_fee_discount(t, motif='social', amount=40000)
        # net = 240000 − 40000 = 200000 ; payé 100000 → solde 100000
        self.assertEqual(t.balance(), Decimal('100000'))

    def test_refus_trop_percu(self):
        from apps.finance.services import create_fee_discount
        self._pay('235000')          # solde restant = 5000
        t = self._tuition()
        with self.assertRaises(ValueError):
            create_fee_discount(t, motif='gesture', amount=20000)   # 20000 > 5000 → refus

    def test_xor_pourcentage_ou_montant(self):
        from apps.finance.services import create_fee_discount
        t = self._tuition()
        with self.assertRaises(ValueError):
            create_fee_discount(t, motif='fratrie')                       # ni l'un ni l'autre
        with self.assertRaises(ValueError):
            create_fee_discount(t, motif='fratrie', percent=10, amount=5000)  # les deux

    def test_annulation_restaure_le_solde(self):
        from apps.finance.services import create_fee_discount, cancel_fee_discount
        adj = create_fee_discount(self._tuition(), motif='fratrie', percent=10)
        self.assertEqual(self._tuition().balance(), Decimal('216000'))
        cancel_fee_discount(adj, cancelled_by=self.director)
        self.assertEqual(self._tuition().adjustments_total(), Decimal('0'))
        self.assertEqual(self._tuition().balance(), Decimal('240000'))    # solde restauré

    def test_gratuite_totale_statut_paye(self):
        from apps.finance.services import create_fee_discount
        from apps.finance.models import DebtStatus
        t = self._tuition()
        create_fee_discount(t, motif='relation', percent=100)
        self.assertEqual(t.net_due(), Decimal('0'))
        self.assertEqual(t.status(), DebtStatus.PAID)                     # rien à payer = payé

    def test_summary_reflete_la_remise(self):
        from apps.finance.services import create_fee_discount, student_fee_summary
        create_fee_discount(self._tuition(), motif='fratrie', percent=10)
        s = student_fee_summary(self.student)
        self.assertEqual(s['due'], Decimal('240000'))
        self.assertEqual(s['adjustments'], Decimal('24000'))
        self.assertEqual(s['balance'], Decimal('216000'))

    def test_grant_view_applique_remise(self):
        # Flux vue : POST d'accord de remise → moteur appelé → solde net correct.
        from django.urls import reverse
        from apps.accounts.models import Membership
        Membership.objects.create(
            user=self.director, school=self.school, role=UserRole.DIRECTOR, is_default=True,
        )
        self.client.force_login(self.director)
        session = self.client.session
        session['active_school_id'] = self.school.id
        session.save()
        resp = self.client.post(
            reverse('finance:discount-grant', args=[self.student.id]), {
                'debt_id': self._tuition().id, 'motif': 'fratrie',
                'value_type': 'percent', 'value': '10',
                'funding_source': 'school', 'justification': '2e enfant',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._tuition().balance(), Decimal('216000'))

    def test_report_agrege_motif_et_financement(self):
        from apps.finance.services import create_fee_discount, discount_report
        t = self._tuition()
        create_fee_discount(t, motif='fratrie', percent=10)                         # 24000, école
        create_fee_discount(t, motif='merit', amount=20000, funding_source='donor') # 20000, donateur
        rep = discount_report(school=self.school)
        self.assertEqual(rep['total'], Decimal('44000'))
        self.assertEqual(rep['count'], 2)
        self.assertEqual(rep['school_funded'], Decimal('24000'))   # part école = manque à gagner
        self.assertEqual(rep['covered'], Decimal('20000'))         # donateur = couvert
        motifs = {m['motif']: m['amount'] for m in rep['by_motif']}
        self.assertEqual(motifs['fratrie'], Decimal('24000'))
        self.assertEqual(motifs['merit'], Decimal('20000'))

    def test_report_exclut_les_annulees(self):
        from apps.finance.services import create_fee_discount, cancel_fee_discount, discount_report
        a = create_fee_discount(self._tuition(), motif='fratrie', percent=10)
        cancel_fee_discount(a)
        rep = discount_report(school=self.school)
        self.assertEqual(rep['total'], Decimal('0'))
        self.assertEqual(rep['count'], 0)


class FeeLevelTargetingTests(TestCase):
    """Ciblage des frais par niveau (applies_to_levels) : vide = tous, ciblé = bon niveau
    seulement, non rétroactif (idempotence). Voir FeeType.is_applicable."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École N', short_name='EN', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )
        cls.klass_pre = SchoolClass.objects.create(
            school=cls.school, name='Maternelle', level='prescolaire',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        cls.klass_fond = SchoolClass.objects.create(
            school=cls.school, name='1A', level='fondamental_1',
            annual_fee=Decimal('100000'), max_capacity=40,
        )
        # Obligatoire ciblé PRÉSCOLAIRE uniquement.
        cls.fee_pre = FeeType.objects.create(
            school=cls.school, name='Inscription préscolaire', category=FeeCategory.ONE_TIME,
            default_amount=Decimal('5000'), is_mandatory=True, applies_to=AppliesTo.ALL,
            applies_to_levels=['prescolaire'],
        )
        # Obligatoire TOUS niveaux (liste vide).
        cls.fee_all = FeeType.objects.create(
            school=cls.school, name='Assurance', category=FeeCategory.ONE_TIME,
            default_amount=Decimal('2000'), is_mandatory=True, applies_to=AppliesTo.ALL,
            applies_to_levels=[],
        )

    def _enroll(self, klass):
        s = Student.objects.create(
            school=self.school, school_class=klass, first_name='X', last_name='Y',
            gender='F', tuition_fee=klass.annual_fee,
        )
        enr = StudentEnrollment.objects.create(
            student=s, school=self.school, school_class=klass,
            school_year=self.year, status=EnrollmentStatus.ACTIVE,
        )
        return build_fee_account(enr)

    def test_modele_applies_to_level(self):
        self.assertTrue(self.fee_pre.applies_to_level('prescolaire'))
        self.assertFalse(self.fee_pre.applies_to_level('fondamental_1'))
        self.assertTrue(self.fee_all.applies_to_level('fondamental_1'))   # vide = tous

    def test_frais_cible_au_bon_niveau(self):
        acc = self._enroll(self.klass_pre)
        self.assertTrue(acc.debts.filter(fee_type=self.fee_pre).exists())   # préscolaire ✓
        self.assertTrue(acc.debts.filter(fee_type=self.fee_all).exists())   # tous niveaux ✓

    def test_frais_cible_absent_autre_niveau(self):
        acc = self._enroll(self.klass_fond)
        self.assertFalse(acc.debts.filter(fee_type=self.fee_pre).exists())  # pas préscolaire → absent
        self.assertTrue(acc.debts.filter(fee_type=self.fee_all).exists())   # tous niveaux → présent

    def test_modification_non_retroactive(self):
        # Fiche générée SANS le frais (fondamental) ; on élargit ensuite le frais au fondamental.
        acc = self._enroll(self.klass_fond)
        self.assertFalse(acc.debts.filter(fee_type=self.fee_pre).exists())
        self.fee_pre.applies_to_levels = ['prescolaire', 'fondamental_1']
        self.fee_pre.save()
        # build_fee_account est idempotent → la fiche existante N'EST PAS régénérée.
        acc2 = build_fee_account(acc.enrollment)
        self.assertFalse(acc2.debts.filter(fee_type=self.fee_pre).exists())  # inchangé


class ScheduleTemplateTests(TestCase):
    """Gabarits de tranches personnalisables : découpage exact pour un nombre QUELCONQUE
    de tranches, non-rétroactivité de l'édition, unicité du nom, un seul défaut."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name='École G', short_name='EG', city='Bamako', school_type='primary',
        )
        cls.year = SchoolYear.objects.create(
            school=cls.school, name='2025-2026',
            start_date=date(2025, 10, 1), end_date=date(2026, 6, 30), is_active=True,
        )

    _seq = 0

    def _enrollment(self, annual_fee):
        """Crée classe + élève + inscription actifs pour un montant de scolarité donné."""
        ScheduleTemplateTests._seq += 1
        n = ScheduleTemplateTests._seq
        klass = SchoolClass.objects.create(
            school=self.school, name=f'C{n}', level='fondamental_1',
            annual_fee=Decimal(annual_fee), max_capacity=40,
        )
        student = Student.objects.create(
            school=self.school, school_class=klass, full_name=f'Élève {n}',
            gender='M', tuition_fee=Decimal(annual_fee),
        )
        return StudentEnrollment.objects.create(
            student=student, school=self.school, school_class=klass,
            school_year=self.year, status=EnrollmentStatus.ACTIVE,
        )

    def _tuition_installs(self, account):
        debt = account.debts.get(kind=FeeDebtKind.TUITION)
        return list(debt.installments.order_by('sequence'))

    # ── Découpage pour un nombre quelconque ────────────────────
    def test_gabarit_personnalise_2_tranches(self):
        tpl = PaymentScheduleTemplate.objects.create(
            school=self.school, name='Semestriel', installments_count=2,
        )
        acc = build_fee_account(self._enrollment('244000'), template=tpl)
        amounts = [i.amount_due for i in self._tuition_installs(acc)]
        self.assertEqual(len(amounts), 2)
        self.assertEqual(sum(amounts), Decimal('244000'))          # somme EXACTE
        self.assertEqual(amounts, [Decimal('122000'), Decimal('122000')])

    def test_extreme_12_tranches_montant_a_arrondi(self):
        # 100 001 / 12 = 8333,4… → reste 5 réparti sur les 5 premières. Somme = 100 001.
        tpl = PaymentScheduleTemplate.objects.create(
            school=self.school, name='Douze', installments_count=12,
        )
        acc = build_fee_account(self._enrollment('100001'), template=tpl)
        amounts = [i.amount_due for i in self._tuition_installs(acc)]
        self.assertEqual(len(amounts), 12)
        self.assertEqual(sum(amounts), Decimal('100001'))          # jamais un franc perdu
        self.assertEqual(amounts.count(Decimal('8334')), 5)
        self.assertEqual(amounts.count(Decimal('8333')), 7)

    def test_extreme_1_tranche(self):
        tpl = PaymentScheduleTemplate.objects.create(
            school=self.school, name='Unique', installments_count=1,
        )
        acc = build_fee_account(self._enrollment('75000'), template=tpl)
        amounts = [i.amount_due for i in self._tuition_installs(acc)]
        self.assertEqual(amounts, [Decimal('75000')])              # une seule, montant total

    # ── Non-rétroactivité de l'édition ─────────────────────────
    def test_edition_du_nombre_non_retroactive(self):
        tpl = PaymentScheduleTemplate.objects.create(
            school=self.school, name='Évolutif', installments_count=3,
        )
        acc1 = build_fee_account(self._enrollment('90000'), template=tpl)
        self.assertEqual(len(self._tuition_installs(acc1)), 3)     # inscription faite = 3

        tpl.installments_count = 12                                 # le directeur édite
        tpl.save()

        acc1_reload = self.account_reload(acc1)
        self.assertEqual(len(self._tuition_installs(acc1_reload)), 3)  # figé, inchangé

        acc2 = build_fee_account(self._enrollment('90000'), template=tpl)
        self.assertEqual(len(self._tuition_installs(acc2)), 12)    # nouvelle inscription = 12

    def account_reload(self, account):
        from apps.finance.models import StudentFeeAccount
        return StudentFeeAccount.objects.get(pk=account.pk)

    # ── Invariants de gestion ──────────────────────────────────
    def test_nom_unique_par_ecole(self):
        from django.db import IntegrityError, transaction
        PaymentScheduleTemplate.objects.create(
            school=self.school, name='Doublon', installments_count=2,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentScheduleTemplate.objects.create(
                    school=self.school, name='Doublon', installments_count=4,
                )

    def test_un_seul_defaut_par_ecole(self):
        a = PaymentScheduleTemplate.objects.create(
            school=self.school, name='A', installments_count=2, is_default=True,
        )
        b = PaymentScheduleTemplate.objects.create(
            school=self.school, name='B', installments_count=4, is_default=True,
        )
        a.refresh_from_db()
        self.assertFalse(a.is_default)                             # B a démoté A
        self.assertTrue(PaymentScheduleTemplate.objects.get(pk=b.pk).is_default)
        self.assertEqual(
            PaymentScheduleTemplate.objects.filter(school=self.school, is_default=True).count(), 1,
        )
