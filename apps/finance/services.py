"""
Module Finances — Lot 3 : génération de la fiche financière & allocation des paiements.

Fonctions pures (pas d'effet de bord caché, transactions explicites) consommées par :
  - la commande de test `build_fee_account_for_student` (ce lot),
  - l'inscription enrichie (lot 4) qui passera les frais optionnels choisis,
  - l'écran d'encaissement (lot 5) qui appellera `allocate_payment`.

Rappels de contrat (cf. apps/finance/models.py) :
  - 3 familles de dettes jamais fondues ; allocation FIFO INTRA-dette.
  - Payment immuable ; le lien passe par PaymentAllocation ; aucun solde stocké.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import (
    Sum, F, OuterRef, Subquery, Exists, Case, When, Value, CharField, DecimalField,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.students.models import StudentEnrollment
from apps.schools.periods import periods_for_class
from .models import (
    FeeType, FeeCategory, AppliesTo,
    StudentFeeAccount, FeeDebt, FeeDebtKind, Installment, PaymentAllocation,
    PaymentScheduleTemplate, FeeAdjustment,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 0. Reconnaissance nouveau / ancien (socle temporel — lot 1)
# ═══════════════════════════════════════════════════════════════════════════════

def is_returning_student(enrollment):
    """
    True si l'élève est un ANCIEN (réinscription) : il possède déjà un StudentEnrollment
    pour une année ANTÉRIEURE dans la même école.

    Règle : on compare les start_date des SchoolYear. Si l'enrollment courant n'a pas
    d'année rattachée (cas legacy), on retombe sur « a-t-il une autre inscription ? ».
    """
    sy = enrollment.school_year
    others = (
        StudentEnrollment.objects
        .filter(student=enrollment.student, school=enrollment.school)
        .exclude(pk=enrollment.pk)
    )
    if sy and sy.start_date:
        return others.filter(school_year__start_date__lt=sy.start_date).exists()
    return others.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Construction de la fiche financière d'un enrollment
# ═══════════════════════════════════════════════════════════════════════════════

def build_fee_account(enrollment, fee_selections=None, template=None):
    """
    Crée (ou retourne) le StudentFeeAccount d'un enrollment, avec ses dettes.

    Génère :
      - la SCOLARITÉ (kind=tuition) depuis enrollment.school_class.annual_fee, découpée
        par `template` (gabarit choisi à l'inscription) sinon le gabarit par défaut ;
      - les frais OBLIGATOIRES applicables (applies_to vs nouveau/ancien) ;
      - les frais OPTIONNELS choisis à l'inscription, via `fee_selections`.

    `fee_selections` (lot 4a — inscription unitaire) : liste de dicts
        [{'fee_type_id': int, 'variant_id': int|None}, …]
      décrivant les options cochées (tenue, fournitures, cantine, bus…). Pour groupe et
      import, on appelle SANS fee_selections → seulement scolarité + frais obligatoires
      (mode « minimal »). L'enrichissement options de l'import = lot 4b.

    DÉCISIONS ACTÉES (cf. FINANCE_MODULE_PLAN.md) :
      - ONE_TIME (inscription, tenue, fournitures) → 1 dette + 1 tranche (éch. = rentrée).
      - SUBSCRIPTION (bus, cantine) :
          * choisi à l'inscription   → dette is_active=True, MAIS AUCUNE mensualité
            générée d'avance ; la 1ère mensualité naîtra au paiement (lot 5) ;
          * obligatoire non choisi   → dette is_active=False (mécanique prête).
      - TENUE → variante auto selon student.gender ; BUS → variante = trajet choisi.

    IDEMPOTENT : fiche existant DÉJÀ AVEC des dettes → retournée telle quelle (on ne
    reconstruit pas un échéancier possiblement déjà payé).
    """
    school = enrollment.school
    ensure_default_schedule_templates(school)   # jamais d'école sans gabarit de tranches
    school_class = enrollment.school_class
    student = enrollment.student
    is_returning = is_returning_student(enrollment)

    with transaction.atomic():
        account, _created = StudentFeeAccount.objects.get_or_create(enrollment=enrollment)

        # Garde-fou d'idempotence : déjà des dettes → on ne touche à rien.
        if account.debts.exists():
            return account

        # ── 1) Scolarité (toujours, si la classe porte un montant) ──────────────
        annual_fee = school_class.annual_fee or Decimal('0')
        if annual_fee > 0:
            tuition_debt = FeeDebt.objects.create(
                account=account, fee_type=None, variant=None,
                kind=FeeDebtKind.TUITION, label='Scolarité',
                total_amount=annual_fee,
            )
            tpl = template or (
                PaymentScheduleTemplate.objects
                .filter(school=school, is_default=True, is_active=True).first()
            )
            periods = []
            if enrollment.school_year_id:
                # Périodes du cycle de la classe de l'élève (compositions / trimestres).
                periods = list(periods_for_class(enrollment.school_class, enrollment.school_year))
            generate_tuition_installments(tuition_debt, tpl, periods)

        rentree = _start_date_for(enrollment)
        processed_ids = set()  # anti double-comptage entre obligatoires et options

        # ── 2) Frais OBLIGATOIRES applicables (hors scolarité) ──────────────────
        mandatory_fees = (
            FeeType.objects
            .filter(school=school, is_active=True, is_mandatory=True)
            .exclude(category=FeeCategory.TUITION)
            .order_by('order', 'name')
        )
        for fee in mandatory_fees:
            if not fee.applies_to_student(is_returning):
                continue
            # Abonnement obligatoire → inactif (pas d'activation automatique).
            _make_debt(account, fee, is_returning, student, rentree,
                       activate_subscription=False)
            processed_ids.add(fee.id)

        # ── 3) Frais OPTIONNELS choisis à l'inscription ─────────────────────────
        for sel in (fee_selections or []):
            fid = sel.get('fee_type_id')
            if not fid or fid in processed_ids:
                continue
            fee = (
                FeeType.objects
                .filter(school=school, id=fid, is_active=True)
                .exclude(category=FeeCategory.TUITION)
                .first()
            )
            if fee is None:
                continue
            # Variante explicitement choisie (bus = trajet). Ignorée pour les frais
            # genrés (résolus automatiquement par le genre dans _make_debt).
            chosen_variant = None
            vid = sel.get('variant_id')
            if vid:
                chosen_variant = fee.variants.filter(id=vid, is_active=True).first()
            # Une option cochée = on l'active (abonnement is_active=True).
            _make_debt(account, fee, is_returning, student, rentree,
                       chosen_variant=chosen_variant, activate_subscription=True)
            processed_ids.add(fid)

        return account


def _make_debt(account, fee, is_returning, student, rentree,
               chosen_variant=None, activate_subscription=False):
    """
    Crée la FeeDebt (+ tranche si ponctuel) pour un frais donné. Retourne la dette,
    ou None si rien à facturer (variante introuvable / montant nul).

    Résolution de la variante :
      - frais genré (tenue)         → variante auto selon student.gender ;
      - frais à variantes non genré → variante = chosen_variant (trajet bus). Requise :
        sans elle, on saute (pas de montant fiable) ;
      - frais simple                → pas de variante.
    """
    variant = chosen_variant
    if fee.has_variants and fee.is_gender_based:
        g = student.gender
        variant = fee.variants.filter(is_active=True, gender_key=g).first() if g else None
        if variant is None:
            # Genre absent ou pas de variante correspondante → on ne devine pas.
            return None
    elif fee.has_variants and not fee.is_gender_based and variant is None:
        return None

    amount = fee.resolved_amount(is_returning, variant=variant)
    if amount is None:
        return None

    label = fee.name if variant is None else f'{fee.name} — {variant.label}'

    if fee.category == FeeCategory.SUBSCRIPTION:
        # Abonnement : aucune mensualité générée d'avance (cf. décision actée).
        return FeeDebt.objects.create(
            account=account, fee_type=fee, variant=variant,
            kind=FeeDebtKind.SUBSCRIPTION, label=label,
            total_amount=amount, is_active=activate_subscription,
        )
    # ONE_TIME : 1 dette + 1 tranche échue à la rentrée.
    debt = FeeDebt.objects.create(
        account=account, fee_type=fee, variant=variant,
        kind=FeeDebtKind.ONE_TIME, label=label, total_amount=amount,
    )
    Installment.objects.create(
        debt=debt, sequence=1, amount_due=amount, due_date=rentree, label=label,
    )
    return debt


def build_fee_accounts_bulk(enrollments):
    """
    Version VOLUME de build_fee_account, pour l'import de masse (lot 4b).

    Génère, pour une liste d'enrollments de la MÊME école et MÊME année active, la
    fiche financière de chacun en un nombre de requêtes CONSTANT (≈10) au lieu de
    ~10×N : tout le catalogue/gabarit/périodes est préchargé UNE fois hors boucle, et
    les StudentFeeAccount / FeeDebt / Installment sont créés en 3 bulk_create.

    Périmètre (décision actée import) : scolarité (gabarit par défaut) + frais
    OBLIGATOIRES applicables + tenue auto par genre. AUCUNE option facultative
    (bus/cantine/ponctuels optionnels) — celles-ci se cochent élève par élève dans
    l'inscription individuelle. La version unitaire build_fee_account reste utilisée
    telle quelle par l'inscription individuelle (avec options).

    Pré-requis : chaque enrollment porte déjà en mémoire son .student (avec gender) et
    son .school_class (avec annual_fee) — c'est le cas après l'import (objets réutilisés),
    donc zéro requête N+1 pour y accéder. Idempotent : les enrollments ayant déjà une
    fiche sont ignorés.
    """
    if not enrollments:
        return []

    school = enrollments[0].school
    ensure_default_schedule_templates(school)   # jamais d'école sans gabarit de tranches
    active_year = enrollments[0].school_year

    # ── Préchargement UNIQUE (hors boucle) ──────────────────────────────────────
    mandatory_fees = list(
        FeeType.objects
        .filter(school=school, is_active=True, is_mandatory=True)
        .exclude(category=FeeCategory.TUITION)
        .prefetch_related('variants')
        .order_by('order', 'name')
    )
    template = (
        PaymentScheduleTemplate.objects
        .filter(school=school, is_default=True, is_active=True).first()
    )
    # Périodes du cycle de la classe du lot (import généralement homogène par classe) ;
    # sert seulement aux dates d'échéance, avec repli sûr sur les segments d'année.
    periods = list(periods_for_class(enrollments[0].school_class, active_year)) if active_year else []
    n_tuition = _template_count(template)
    tuition_due_dates, tuition_labels = _due_dates_for_year(active_year, n_tuition, periods)
    rentree = _start_date_for(enrollments[0])

    # Anciens (réinscriptions) parmi le lot — 1 seule requête (vide pour des imports
    # de nouveaux élèves, mais correct dans le cas général).
    returning_ids = set()
    if active_year and active_year.start_date:
        returning_ids = set(
            StudentEnrollment.objects
            .filter(student_id__in=[e.student_id for e in enrollments], school=school,
                    school_year__start_date__lt=active_year.start_date)
            .values_list('student_id', flat=True)
        )

    # Idempotence : on saute les enrollments ayant déjà une fiche (1 requête).
    already = set(
        StudentFeeAccount.objects
        .filter(enrollment__in=enrollments)
        .values_list('enrollment_id', flat=True)
    )
    todo = [e for e in enrollments if e.id not in already]
    if not todo:
        return []

    with transaction.atomic():
        # 1) Fiches (bulk). PostgreSQL renseigne les PK → on peut les référencer ensuite.
        accounts = StudentFeeAccount.objects.bulk_create(
            [StudentFeeAccount(enrollment=e) for e in todo]
        )
        acc_by_enroll = {e.id: acc for e, acc in zip(todo, accounts)}

        # 2) Dettes (bulk) + plan d'échéances parallèle (même ordre que les dettes créées).
        debt_objs, debt_plan = [], []
        for e in todo:
            acc = acc_by_enroll[e.id]
            is_ret = e.student_id in returning_ids

            annual = int(e.school_class.annual_fee or 0)
            if annual > 0:
                debt_objs.append(FeeDebt(
                    account=acc, fee_type=None, variant=None,
                    kind=FeeDebtKind.TUITION, label='Scolarité', total_amount=annual,
                ))
                debt_plan.append(('tuition', annual, 'Scolarité'))

            for fee in mandatory_fees:
                if not fee.applies_to_student(is_ret):
                    continue
                variant = None
                if fee.has_variants:
                    if fee.is_gender_based:
                        g = e.student.gender
                        # variantes préchargées → recherche en mémoire (pas de requête)
                        variant = next(
                            (v for v in fee.variants.all() if v.is_active and v.gender_key == g),
                            None,
                        ) if g else None
                        if variant is None:
                            continue  # genre absent / pas de variante → on saute
                    else:
                        continue      # variante à choix manuel → pas à l'import
                amount = fee.resolved_amount(is_ret, variant=variant)
                if amount is None:
                    continue
                label = fee.name if variant is None else f'{fee.name} — {variant.label}'
                if fee.category == FeeCategory.SUBSCRIPTION:
                    debt_objs.append(FeeDebt(
                        account=acc, fee_type=fee, variant=variant,
                        kind=FeeDebtKind.SUBSCRIPTION, label=label,
                        total_amount=amount, is_active=False,
                    ))
                    debt_plan.append(('subscription', amount, label))  # pas de tranche
                else:
                    debt_objs.append(FeeDebt(
                        account=acc, fee_type=fee, variant=variant,
                        kind=FeeDebtKind.ONE_TIME, label=label, total_amount=amount,
                    ))
                    debt_plan.append(('one_time', amount, label))

        created_debts = FeeDebt.objects.bulk_create(debt_objs)

        # 3) Tranches (bulk) à partir du plan.
        inst_objs = []
        for debt, (kind, amount, label) in zip(created_debts, debt_plan):
            if kind == 'tuition':
                parts = _split_amount(int(amount), n_tuition)
                for i in range(n_tuition):
                    inst_objs.append(Installment(
                        debt=debt, sequence=i + 1, amount_due=parts[i],
                        due_date=tuition_due_dates[i], label=tuition_labels[i],
                    ))
            elif kind == 'one_time':
                inst_objs.append(Installment(
                    debt=debt, sequence=1, amount_due=amount,
                    due_date=rentree, label=label,
                ))
            # subscription : aucune mensualité d'avance

        Installment.objects.bulk_create(inst_objs)

    return accounts


def _start_date_for(enrollment):
    """Date de rentrée : début de l'année active si dispo, sinon aujourd'hui."""
    from datetime import date
    sy = enrollment.school_year
    if sy and sy.start_date:
        return sy.start_date
    return date.today()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Découpage de la scolarité en tranches datées
# ═══════════════════════════════════════════════════════════════════════════════

# Gabarits de tranches standards, provisionnés automatiquement pour toute école.
_STANDARD_SCHEDULE_TEMPLATES = [('Annuel', 1), ('Trimestriel', 3), ('Mensuel', 9)]
_DEFAULT_SCHEDULE_NAME = 'Trimestriel'


def ensure_default_schedule_templates(school):
    """Garantit que l'école possède les 3 gabarits standards (Annuel / Trimestriel /
    Mensuel), **Trimestriel par défaut**. Idempotent : ne fait RIEN si l'école a déjà
    au moins un gabarit (on ne réécrit jamais le choix du directeur). Retourne True si
    des gabarits ont été créés. Vaut pour les nouvelles écoles comme pour les anciennes
    laissées vides — appelé à l'ouverture de l'écran Frais et à la génération des frais."""
    if school is None or PaymentScheduleTemplate.objects.filter(school=school).exists():
        return False
    for name, count in _STANDARD_SCHEDULE_TEMPLATES:
        PaymentScheduleTemplate.objects.create(
            school=school, name=name, installments_count=count,
            is_active=True, is_default=(name == _DEFAULT_SCHEDULE_NAME),
        )
    return True


def generate_tuition_installments(debt, template, periods):
    """
    Génère les Installment d'une dette de SCOLARITÉ.

    Nombre de tranches : template.installments_count (1 = paiement unique si pas de
    gabarit par défaut). Montants : total découpé en N parts, le RESTE de division
    réparti sur les premières tranches → la somme des tranches == total EXACT (jamais
    un franc perdu : 100000/3 → 33334 + 33333 + 33333).

    Dates limites (règle de dérivation) :
      - si N == nombre de Period fournies → une tranche par période, due_date = fin de
        période, label = nom de période ;
      - sinon → on répartit sur la durée de l'année (SchoolYear.start_date→end_date) en
        N segments égaux, due_date = fin de chaque segment (dernier = end_date) ;
      - si l'année n'a pas de dates exploitables → repli mensuel à partir de la rentrée.

    Idempotent : si la dette a déjà des tranches, on ne régénère pas.
    """
    if debt.installments.exists():
        return list(debt.installments.all())

    n = _template_count(template)
    amounts = _split_amount(int(debt.total_amount), n)
    due_dates, labels = _due_dates_for_year(debt.account.enrollment.school_year, n, periods)

    installments = [
        Installment(
            debt=debt, sequence=i + 1,
            amount_due=amounts[i], due_date=due_dates[i], label=labels[i],
        )
        for i in range(n)
    ]
    Installment.objects.bulk_create(installments)
    return installments


# ── Helpers de découpage (réutilisés par la version unitaire ET la version bulk) ──

def _template_count(template):
    """Nombre de tranches d'un gabarit (1 si pas de gabarit → repli annuel)."""
    return max(int(template.installments_count) if template else 1, 1)


def _split_amount(total, n):
    """Découpe `total` (FCFA entiers) en n parts, le reste réparti sur les premières.
    Garantit Σ parts == total (jamais un franc perdu : 100000/3 → 33334+33333+33333)."""
    base = total // n
    remainder = total - base * n
    return [base + (1 if i < remainder else 0) for i in range(n)]


def _due_dates_for_year(school_year, n, periods):
    """
    (due_dates, labels) pour n tranches sur une année scolaire :
      - n == nb de périodes → une tranche par période (due = fin de période, label = nom) ;
      - sinon, année datée   → n segments égaux (due = fin de chaque segment) ;
      - sinon (repli)        → mensualités à partir de la rentrée (~30 j).
    Ne dépend QUE de l'année (pas d'une dette) → utilisable en lot pour tout un import.
    """
    from datetime import date, timedelta

    # Une tranche par période : seulement si toutes les périodes sont datées
    # (dates optionnelles) et que le nombre coïncide.
    if periods and n == len(periods) and all(p.end_date for p in periods):
        return [p.end_date for p in periods], [p.name for p in periods]

    start = school_year.start_date if (school_year and school_year.start_date) else date.today()
    end = school_year.end_date if (school_year and school_year.end_date) else None

    if end and end > start:
        span = (end - start).days
        due = [start + timedelta(days=round(span * i / n)) for i in range(1, n + 1)]
    else:
        due = [start + timedelta(days=30 * (i + 1)) for i in range(n)]

    return due, [f'Tranche {i + 1}' for i in range(n)]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Allocation d'un paiement (FIFO intra-dette)
# ═══════════════════════════════════════════════════════════════════════════════

def allocate_payment(payment, target, strategy='fifo'):
    """
    Ventile un Payment vers les Installment d'UNE dette (jamais en travers des familles).

    `target` peut être :
      - une FeeDebt      → FIFO sur ses tranches (la plus ancienne non soldée d'abord) ;
      - un Installment   → alloue uniquement sur cette tranche.

    Garanties :
      - on ne dépasse JAMAIS payment.amount (on tient compte des allocations déjà
        faites par ce même paiement) ;
      - on ne dépasse jamais le solde d'une tranche ;
      - chaque allocation a un montant > 0 ;
      - tout reste à l'intérieur de la dette ciblée → pas de fuite inter-familles.

    Retourne la liste des PaymentAllocation créées.
    """
    if isinstance(target, Installment):
        installments = [target]
    elif isinstance(target, FeeDebt):
        # FIFO : tranches par ordre (sequence), la plus ancienne d'abord.
        installments = list(target.installments.order_by('sequence', 'due_date'))
    else:
        raise TypeError('target doit être une FeeDebt ou un Installment.')

    created = []
    with transaction.atomic():
        # Reste disponible = montant du paiement − ce que CE paiement a déjà alloué
        # ailleurs (anti sur-allocation, y compris en cas d'appels successifs).
        already = (
            PaymentAllocation.objects.filter(payment=payment)
            .aggregate(s=Sum('amount'))['s'] or Decimal('0')
        )
        remaining = Decimal(payment.amount) - already
        if remaining <= 0:
            return created

        for inst in installments:
            if remaining <= 0:
                break
            inst_balance = inst.balance()
            if inst_balance <= 0:
                continue
            alloc_amount = min(remaining, inst_balance)
            if alloc_amount <= 0:
                continue
            created.append(PaymentAllocation.objects.create(
                payment=payment, installment=inst, amount=alloc_amount,
            ))
            remaining -= alloc_amount

    return created


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Encaissement au guichet (lot 5) — pay-as-you-go abonnements, plan d'allocation
# ═══════════════════════════════════════════════════════════════════════════════

from datetime import date as _date2  # noqa: E402 (import local au bloc lot 5)

_FR_MONTHS = [
    '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
]


def _subscription_target_months(debt, n_months, today=None):
    """
    Liste ordonnée des mois à couvrir pour un abonnement payé au guichet, à partir du
    mois courant : [(label, due_date, year, month), …].

    n_months=1 → uniquement le mois courant (pay-as-you-go).
    n_months>1 → mois courant + suivants (option « payer l'année »), bornés à la fin de
    l'année scolaire si on peut la connaître (via debt.account.enrollment.school_year).
    """
    today = today or _date2.today()
    y, m = today.year, today.month

    # Borne haute = fin de l'année scolaire si disponible (sinon pas de borne).
    end = None
    sy = debt.account.enrollment.school_year
    if sy and sy.end_date:
        end = (sy.end_date.year, sy.end_date.month)

    months = []
    for _ in range(max(int(n_months), 1)):
        if end and (y, m) > end:
            break
        # due_date = 1er du mois (échéance « début de mois » pour une mensualité).
        months.append((f'{_FR_MONTHS[m]} {y}', _date2(y, m, 1), y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def generate_subscription_installments(debt, n_months=1, today=None):
    """
    Génère, pour un abonnement (FeeDebt kind=subscription), les Installment manquants
    des mois ciblés à partir du mois courant. PAS de dette d'avance : on ne crée la
    mensualité qu'au moment où le guichetier choisit de l'encaisser (pay-as-you-go).

    IDEMPOTENT : un mois déjà émis (un Installment dont la due_date tombe ce mois) n'est
    jamais dupliqué. Retourne la liste des Installment correspondant aux mois ciblés
    (existants + créés), dans l'ordre chronologique → prête pour l'allocation FIFO.
    """
    if debt.kind != FeeDebtKind.SUBSCRIPTION:
        return list(debt.installments.order_by('sequence'))

    targets = _subscription_target_months(debt, n_months, today)
    existing = list(debt.installments.all())
    by_month = {(i.due_date.year, i.due_date.month): i for i in existing}
    next_seq = (max((i.sequence for i in existing), default=0)) + 1
    monthly = debt.total_amount  # total_amount d'un abonnement = la MENSUALITÉ (snapshot)

    result = []
    to_create = []
    for label, due, y, m in targets:
        inst = by_month.get((y, m))
        if inst is None:
            inst = Installment(
                debt=debt, sequence=next_seq, amount_due=monthly,
                due_date=due, label=label,
            )
            next_seq += 1
            to_create.append(inst)
        result.append(inst)
    if to_create:
        Installment.objects.bulk_create(to_create)
    return result


def allocation_plan(debt, amount, subscription_months=1, today=None):
    """
    SIMULE (sans rien enregistrer) la ventilation FIFO de `amount` sur la dette `debt`,
    pour l'aperçu en direct du guichet.

    Renvoie (plan, overflow) :
      - plan : liste de dicts {label, due_date, amount (alloué), full (bool), balance} ;
      - overflow : montant qui ne tomberait nulle part (trop-perçu) → > 0 = à signaler.

    Pour un abonnement, on inclut les mensualités PROSPECTIVES (mois courant + n-1) qui
    seraient générées à l'encaissement, pour que l'aperçu reflète la réalité.
    """
    amount = Decimal(amount or 0)
    items = []  # (label, due_date, balance_restant)

    if debt.kind == FeeDebtKind.SUBSCRIPTION:
        existing = list(debt.installments.all())
        by_month = {(i.due_date.year, i.due_date.month): i for i in existing}
        for label, due, y, m in _subscription_target_months(debt, subscription_months, today):
            inst = by_month.get((y, m))
            bal = inst.balance() if inst else debt.total_amount
            if bal > 0:
                items.append((label, due, bal))
    else:
        for inst in debt.installments.order_by('sequence', 'due_date'):
            bal = inst.balance()
            if bal > 0:
                items.append((inst.label, inst.due_date, bal))

    plan = []
    remaining = amount
    for label, due, bal in items:
        if remaining <= 0:
            break
        take = min(remaining, bal)
        if take <= 0:
            continue
        plan.append({'label': label, 'due_date': due, 'amount': take,
                     'full': take >= bal, 'balance': bal,
                     'remaining_after': bal - take})
        remaining -= take
    return plan, remaining


def payable_targets(account, today=None):
    """
    Familles encaissables d'une fiche, pour le sélecteur du panneau de guichet.

    Une « cible » = une FeeDebt sur laquelle il reste quelque chose à payer :
      - TUITION / ONE_TIME → incluse si balance() > 0 (solde restant) ;
      - SUBSCRIPTION active → toujours incluse (pay-as-you-go) ; le « dû » affiché est
        le solde du mois courant s'il existe, sinon la mensualité (qui sera générée).
    Retourne une liste de dicts triés (les plus en retard d'abord) prête pour le template.
    """
    today = today or _date2.today()
    targets = []
    for debt in account.debts.filter(is_active=True).order_by('kind', 'created_at'):
        if debt.kind == FeeDebtKind.SUBSCRIPTION:
            # Solde du mois courant (mensualité − déjà payé ce mois), sinon la mensualité.
            cur = next((i for i in debt.installments.all()
                        if i.due_date.year == today.year and i.due_date.month == today.month), None)
            due_now = cur.balance() if cur else debt.total_amount
            targets.append({
                'debt_id': debt.id, 'kind': debt.kind, 'label': debt.label,
                'is_subscription': True, 'monthly': int(debt.total_amount),
                'due_now': int(due_now), 'overdue': False,
            })
        else:
            bal = debt.balance()
            if bal <= 0:
                continue
            # En retard si une tranche de cette dette est dépassée.
            overdue = any(i.is_overdue(today) for i in debt.installments.all())
            targets.append({
                'debt_id': debt.id, 'kind': debt.kind, 'label': debt.label,
                'is_subscription': False, 'monthly': None,
                'due_now': int(bal), 'overdue': overdue,
            })
    # Les plus en retard d'abord (pour pré-sélectionner la cible prioritaire).
    targets.sort(key=lambda t: (not t['overdue'], t['kind']))
    return targets


def timeline_families(account):
    """
    Regroupe les dettes ACTIVES d'une fiche en 3 familles ordonnées, pour la timeline.
    Retourne [(label, [FeeDebt, …]), …] sans les familles vides. Source unique partagée
    par la fiche élève (consultation) et le re-render après encaissement.
    """
    if account is None:
        return []
    debts = list(account.debts.all())
    ordered = [
        ('Scolarité',       FeeDebtKind.TUITION),
        ('Frais ponctuels', FeeDebtKind.ONE_TIME),
        ('Abonnements',     FeeDebtKind.SUBSCRIPTION),
    ]
    families = [
        (label, [d for d in debts if d.kind == kind and d.is_active])
        for label, kind in ordered
    ]
    return [(label, ds) for label, ds in families if ds]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. HELPER FINANCIER CENTRAL (lot 6bis-A) — source unique de vérité du solde
# ═══════════════════════════════════════════════════════════════════════════════
#
# Tous les écrans qui affichent un solde élève DOIVENT passer par ces helpers, pour
# gérer le cas « élève SANS fiche financière » de façon UNIFORME :
#   - per-objet  : student_fee_summary(student) → dict | None  (None = pas de fiche)
#   - par qs élèves : annotate_students_with_fees(qs)  (statut 'no_fee' si pas de fiche)
#   - par qs fiches : fee_accounts_annotated(...)  (agrégats dû/versé/solde des fiches)
#
# CONTRAT « SANS FICHE » : None / 'no_fee'. Chaque écran le rend par un ÉTAT NEUTRE
# (gris « — »), JAMAIS par un défaut rouge « Impayé » (un élève sans fiche n'est pas
# impayé, il n'a simplement pas encore de fiche). Les agrégats (totaux, taux) ne
# comptent QUE les fiches ; le nombre d'élèves sans fiche est exposé À PART.


def _due_subquery(account_ref):
    """Σ des dettes actives d'une fiche (sous-requête corrélée)."""
    return (
        FeeDebt.objects.filter(account=account_ref, is_active=True)
        .values('account').annotate(s=Sum('total_amount')).values('s')
    )


def _paid_subquery(account_ref):
    """Σ des allocations affectées aux tranches d'une fiche (sous-requête corrélée)."""
    return (
        PaymentAllocation.objects.filter(installment__debt__account=account_ref)
        .values('installment__debt__account').annotate(s=Sum('amount')).values('s')
    )


def _adj_subquery(account_ref):
    """Σ des remises ACTIVES (non annulées) des dettes d'une fiche (valeurs FCFA figées)."""
    return (
        FeeAdjustment.objects.filter(debt__account=account_ref, is_cancelled=False)
        .values('debt__account').annotate(s=Sum('resolved_amount')).values('s')
    )


def fee_accounts_annotated(school=None, school_ids=None):
    """
    Queryset de StudentFeeAccount ACTIVES, annotées `due` / `paid` / `balance`
    (les 3 familles, par allocation), en sous-requêtes (pas de Sum multi-jointures).

    Source unique consommée par la page Paiements (lot 6), la liste élèves, le
    dashboard et le promoteur. Filtrable par école (`school`) ou groupe (`school_ids`).
    Les élèves sans fiche ne sont, par nature, PAS dans ce queryset → les agréger ici
    ne les compte jamais (ce qui est voulu : on les expose à part, cf. count_without_account).
    """
    qs = StudentFeeAccount.objects.filter(
        enrollment__status='active', enrollment__student__is_active=True,
    )
    if school is not None:
        qs = qs.filter(enrollment__school=school)
    if school_ids is not None:
        qs = qs.filter(enrollment__school_id__in=school_ids)
    return (
        qs.select_related('enrollment__student__school_class')
        .annotate(
            due=Coalesce(Subquery(_due_subquery(OuterRef('pk')), output_field=DecimalField()), Decimal('0')),
            paid=Coalesce(Subquery(_paid_subquery(OuterRef('pk')), output_field=DecimalField()), Decimal('0')),
            adj=Coalesce(Subquery(_adj_subquery(OuterRef('pk')), output_field=DecimalField()), Decimal('0')),
        )
        .annotate(balance=F('due') - F('adj') - F('paid'))
    )


def count_without_account(school):
    """Nb d'élèves actifs SANS fiche financière active (le « trou » à exposer à part)."""
    total = StudentEnrollment.objects.none()  # placeholder pour lisibilité
    from apps.students.models import Student
    total_active = Student.objects.filter(school=school, is_active=True).count()
    with_account = fee_accounts_annotated(school=school).count()
    return max(total_active - with_account, 0)


def annotate_students_with_fees(student_qs):
    """
    Annote un queryset d'ÉLÈVES avec leur situation financière (via la fiche de
    l'enrollment actif), en gardant les élèves SANS fiche (statut 'no_fee') :
      - has_fee_account : bool
      - fee_due / fee_paid / fee_balance : montants (0 si pas de fiche)
      - fee_status : 'no_fee' | 'paid' | 'partial' | 'unpaid'  (jamais rouge si no_fee)

    Une seule requête (sous-requêtes corrélées) → pas de N+1 sur une liste d'élèves.
    """
    active_acc = StudentFeeAccount.objects.filter(
        enrollment__student=OuterRef('pk'), enrollment__status='active',
    )
    due_sq = (
        FeeDebt.objects
        .filter(account__enrollment__student=OuterRef('pk'),
                account__enrollment__status='active', is_active=True)
        .values('account__enrollment__student')
        .annotate(s=Sum('total_amount')).values('s')
    )
    paid_sq = (
        PaymentAllocation.objects
        .filter(installment__debt__account__enrollment__student=OuterRef('pk'),
                installment__debt__account__enrollment__status='active')
        .values('installment__debt__account__enrollment__student')
        .annotate(s=Sum('amount')).values('s')
    )
    adj_sq = (
        FeeAdjustment.objects
        .filter(debt__account__enrollment__student=OuterRef('pk'),
                debt__account__enrollment__status='active', is_cancelled=False)
        .values('debt__account__enrollment__student')
        .annotate(s=Sum('resolved_amount')).values('s')
    )
    return (
        student_qs
        .annotate(has_fee_account=Exists(active_acc))
        .annotate(
            fee_due=Coalesce(Subquery(due_sq, output_field=DecimalField()), Decimal('0')),
            fee_paid=Coalesce(Subquery(paid_sq, output_field=DecimalField()), Decimal('0')),
            fee_adj=Coalesce(Subquery(adj_sq, output_field=DecimalField()), Decimal('0')),
        )
        .annotate(fee_balance=F('fee_due') - F('fee_adj') - F('fee_paid'))
        .annotate(fee_status=Case(
            When(has_fee_account=False, then=Value('no_fee')),
            When(fee_balance__lte=0,    then=Value('paid')),
            When(fee_paid__gt=0,        then=Value('partial')),
            default=Value('unpaid'),
            output_field=CharField(),
        ))
    )


def _active_account_for(student):
    """Fiche active d'un élève, annotée due/paid/balance — ou None (pas de fiche)."""
    return (
        fee_accounts_annotated(school=student.school)
        .filter(enrollment__student=student)
        .order_by('-enrollment__school_year__start_date')
        .first()
    )


def student_has_overdue(account, today=None):
    """L'élève a-t-il ≥1 tranche échue impayée sur cette fiche ? (cohérent liste rouge)."""
    today = today or timezone.now().date()
    return (
        Installment.objects
        .filter(debt__account=account, debt__is_active=True, due_date__lt=today)
        .annotate(allocated=Coalesce(Sum('allocations__amount'), Decimal('0'), output_field=DecimalField()))
        .annotate(remaining=F('amount_due') - F('allocated'))
        .filter(remaining__gt=0)
        .exists()
    )


def student_fee_summary(student, today=None):
    """
    Situation financière d'UN élève via sa fiche active. Retourne :
      - None  si l'élève n'a PAS de fiche active → l'appelant DOIT afficher un état
        NEUTRE (« pas de fiche »), jamais un défaut rouge « Impayé » ;
      - sinon un dict {due, paid, balance, status, has_overdue, account} où status ∈
        {'paid','partial','unpaid'} (3 familles, par allocation) et has_overdue = ≥1
        tranche échue impayée (= définition de la liste rouge / badge alerte lot 6).
    """
    acc = _active_account_for(student)
    if acc is None:
        return None
    due, paid, adj = acc.due, acc.paid, acc.adj
    balance = due - adj - paid          # Net dû = officiel − remises − payé
    if balance <= 0:
        status = 'paid'
    elif paid > 0:
        status = 'partial'
    else:
        status = 'unpaid'
    return {
        'due': due, 'paid': paid, 'adjustments': adj, 'balance': balance, 'status': status,
        'has_overdue': student_has_overdue(acc, today), 'account': acc,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Remises (FeeAdjustment) — toute la logique argent vit ICI (jamais dans les vues)
# ═══════════════════════════════════════════════════════════════════════════════

def create_fee_discount(debt, *, motif, funding_source='school', percent=None,
                        amount=None, justification='', created_by=None):
    """Accorde une remise sur une dette. Fige la valeur FCFA et REFUSE tout trop-perçu.

    - percent XOR amount (exactement un des deux).
    - Le tarif officiel (debt.total_amount) n'est jamais touché.
    - Lève ValueError si les paramètres sont invalides, si la remise est ≤ 0, ou si elle
      dépasse le solde restant (elle créerait un trop-perçu) — refus, pas d'avoir au niveau 1.
    """
    if (percent is None) == (amount is None):
        raise ValueError('Indiquez un pourcentage OU un montant fixe (exactement un).')
    if percent is not None:
        resolved = (debt.total_amount * Decimal(str(percent)) / Decimal('100')).quantize(Decimal('1'))
    else:
        resolved = Decimal(str(amount)).quantize(Decimal('1'))
    if resolved <= 0:
        raise ValueError('La remise doit être supérieure à 0.')
    current_balance = debt.balance()
    if resolved > current_balance:
        raise ValueError(
            f'Impossible : cette remise ({int(resolved)} FCFA) dépasse le solde restant '
            f'({int(current_balance)} FCFA) et créerait un trop-perçu.'
        )
    return FeeAdjustment.objects.create(
        debt=debt, motif=motif, funding_source=funding_source,
        percent=percent, amount=amount, resolved_amount=resolved,
        justification=justification, created_by=created_by,
    )


def cancel_fee_discount(adjustment, *, cancelled_by=None):
    """Annule une remise (on ne la modifie jamais : on annule + recrée). Idempotent."""
    if adjustment.is_cancelled:
        return adjustment
    adjustment.is_cancelled = True
    adjustment.cancelled_by = cancelled_by
    adjustment.cancelled_at = timezone.now()
    adjustment.save(update_fields=['is_cancelled', 'cancelled_by', 'cancelled_at'])
    return adjustment
