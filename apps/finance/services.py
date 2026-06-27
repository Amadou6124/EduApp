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

    n = template.installments_count if template else 1
    n = max(int(n), 1)

    # ── Montants : découpe avec report du reste (entiers FCFA) ──────────────────
    total = int(debt.total_amount)
    base = total // n
    remainder = total - base * n  # réparti +1 sur les `remainder` premières tranches
    amounts = [base + (1 if i < remainder else 0) for i in range(n)]

    # ── Dates limites ───────────────────────────────────────────────────────────
    due_dates, labels = _derive_due_dates(debt, n, periods)

    installments = []
    for i in range(n):
        installments.append(Installment(
            debt=debt, sequence=i + 1,
            amount_due=amounts[i], due_date=due_dates[i], label=labels[i],
        ))
    Installment.objects.bulk_create(installments)
    return installments


def _derive_due_dates(debt, n, periods):
    """Retourne (due_dates, labels) selon la règle documentée ci-dessus."""
    from datetime import date, timedelta

    # Cas 1 : N == nombre de périodes → calage sur les périodes.
    if periods and n == len(periods):
        due = [p.end_date for p in periods]
        labels = [p.name for p in periods]
        return due, labels

    # Récupère les bornes de l'année via l'enrollment.
    sy = debt.account.enrollment.school_year
    start = sy.start_date if (sy and sy.start_date) else date.today()
    end = sy.end_date if (sy and sy.end_date) else None

    # Cas 2 : année datée → N segments égaux, due_date = fin de chaque segment.
    if end and end > start:
        span = (end - start).days
        due = []
        for i in range(1, n + 1):
            offset = round(span * i / n)
            due.append(start + timedelta(days=offset))
    else:
        # Cas 3 (repli) : mensualités à partir de la rentrée (~30 j).
        due = [start + timedelta(days=30 * (i + 1)) for i in range(n)]

    labels = [f'Tranche {i + 1}' for i in range(n)]
    return due, labels


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
