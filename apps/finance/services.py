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
from django.db.models import Sum

from apps.students.models import StudentEnrollment
from .models import (
    FeeType, FeeCategory, AppliesTo,
    StudentFeeAccount, FeeDebt, FeeDebtKind, Installment, PaymentAllocation,
    PaymentScheduleTemplate,
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
                periods = list(enrollment.school_year.periods.order_by('order'))
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
    periods = list(active_year.periods.order_by('order')) if active_year else []
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

    if periods and n == len(periods):
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
