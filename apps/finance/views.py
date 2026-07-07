"""
Encaissement au guichet (lot 5).

Flux : depuis la fiche élève, le guichetier ouvre le panneau, choisit la FAMILLE de
destination (Scolarité / Inscription / Bus ce mois…), saisit un montant, voit en direct
où l'argent va tomber (aperçu FIFO), puis encaisse. On crée alors un Payment IMMUABLE
(apps.payments) et on l'alloue aux tranches via PaymentAllocation (apps.finance) — jamais
en travers des familles. Reçu PDF (détaillant l'allocation) + notification parent réutilisés.

Décisions actées :
  - Allocation FIFO INTRA-famille (tranche la plus ancienne non soldée d'abord).
  - Abonnements pay-as-you-go : la mensualité du mois est GÉNÉRÉE à l'encaissement.
  - Jamais de sur-allocation : un montant > solde de la famille est REFUSÉ (message),
    on ne crée pas de Payment à surplus orphelin.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.core.mixins import get_school, director_or_staff_required
from apps.students.models import Student
from apps.payments.models import Payment, PaymentMethod

from .models import StudentFeeAccount, FeeDebt
from .services import (
    payable_targets, allocation_plan, allocate_payment,
    generate_subscription_installments,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _active_account(student, school):
    """Fiche financière de l'enrollment ACTIVE de l'élève (ou None)."""
    return (
        StudentFeeAccount.objects
        .filter(enrollment__student=student, enrollment__status='active',
                enrollment__school=school)
        .select_related('enrollment__school_year')
        .prefetch_related('debts__installments__allocations')
        .order_by('-enrollment__school_year__start_date')
        .first()
    )


def _get_debt(student, school, debt_id):
    """Charge une FeeDebt appartenant bien à la fiche active de l'élève (sécurité)."""
    return get_object_or_404(
        FeeDebt,
        id=debt_id,
        account__enrollment__student=student,
        account__enrollment__school=school,
    )


def _parse_amount(raw):
    """Montant entier > 0, ou None si invalide."""
    try:
        v = int(raw)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _toast(resp, message, msg_type='success', **extra):
    payload = {'showToast': {'message': message, 'type': msg_type}}
    payload.update(extra)
    resp['HX-Trigger'] = json.dumps(payload)
    return resp


# ── Panneau d'encaissement ──────────────────────────────────────────────────────

@login_required
@director_or_staff_required
def collect_panel(request, student_id):
    """Rend le corps du panneau de guichet pour un élève (familles dues + formulaire)."""
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class'),
        id=student_id, school=school, is_active=True,
    )
    account = _active_account(student, school)
    targets = payable_targets(account) if account else []

    return render(request, 'finance/partials/collect_panel.html', {
        'student':         student,
        'account':         account,
        'targets':         targets,
        'payment_methods': PaymentMethod.choices,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def collect_preview(request, student_id):
    """Aperçu en direct (HTMX) : où tomberait le montant saisi pour la famille choisie."""
    school = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school, is_active=True)

    debt_id = request.POST.get('debt_id')
    amount = _parse_amount(request.POST.get('amount'))
    months = 12 if request.POST.get('subscription_scope') == 'year' else 1

    if not debt_id or amount is None:
        return render(request, 'finance/partials/allocation_preview.html', {'plan': None})

    debt = _get_debt(student, school, debt_id)
    plan, overflow = allocation_plan(debt, amount, subscription_months=months)
    return render(request, 'finance/partials/allocation_preview.html', {
        'plan':     plan,
        'overflow': int(overflow),
        'debt':     debt,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def collect_create(request, student_id):
    """Encaisse : crée le Payment immuable puis l'alloue (FIFO) à la famille choisie."""
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class'),
        id=student_id, school=school, is_active=True,
    )

    debt_id = request.POST.get('debt_id')
    amount = _parse_amount(request.POST.get('amount'))
    method = request.POST.get('payment_method') or PaymentMethod.CASH
    notes = request.POST.get('notes', '')
    months = 12 if request.POST.get('subscription_scope') == 'year' else 1

    if not debt_id:
        return _toast(HttpResponse(status=422), 'Choisissez une famille de destination.', 'error')
    if amount is None:
        return _toast(HttpResponse(status=422), 'Montant invalide.', 'error')

    debt = _get_debt(student, school, debt_id)

    # ── Abonnement pay-as-you-go : on génère la/les mensualité(s) AVANT d'allouer ──
    # (mois courant, ou N mois si « payer l'année »). Idempotent.
    if debt.kind == 'subscription':
        generate_subscription_installments(debt, n_months=months)

    # Solde réellement encaissable de la famille = somme des soldes de ses tranches
    # (pour un abonnement : les mensualités générées ; pour le reste : ses tranches).
    debt.refresh_from_db()
    payable = sum((i.balance() for i in debt.installments.all()), 0)
    if payable <= 0:
        return _toast(HttpResponse(status=422), 'Rien à encaisser sur cette famille.', 'info')
    if amount > payable:
        # Jamais de sur-allocation : on refuse plutôt que créer un surplus orphelin.
        return _toast(
            HttpResponse(status=422),
            f'Le montant dépasse le solde de « {debt.label} » ({int(payable):,} FCFA).'.replace(',', ' '),
            'error',
        )

    # ── Payment IMMUABLE (apps.payments) ────────────────────────────────────────
    payment = Payment.objects.create(
        student=student, amount=amount, payment_method=method,
        collected_by=request.user, notes=notes,
    )
    # ── Allocation FIFO intra-famille ───────────────────────────────────────────
    allocations = allocate_payment(payment, debt)

    # Notification parent (jamais bloquante) — mentionne la famille réglée.
    try:
        from apps.notifications.services import notify_guardians
        from apps.notifications.models import NotificationCategory
        notify_guardians(
            student=student, category=NotificationCategory.PAYMENT,
            title='Paiement enregistré',
            body=f'{amount:,.0f} FCFA reçus pour « {debt.label} ».'.replace(',', ' '),
            url=reverse('parent:payments'), target=payment,
        )
    except Exception:
        pass

    from apps.dashboard.views import invalidate_dashboard_cache
    invalidate_dashboard_cache(school)

    # Réponse : on re-rend la timeline (OOB) + toast (avec lien reçu) + fermeture du panneau.
    from .services import timeline_families
    account = _active_account(student, school)
    timeline = render(request, 'finance/partials/timeline.html', {
        'student': student, 'account': account,
        'fee_families': timeline_families(account),
    }).content.decode()
    resp = HttpResponse(f'<div id="fee-timeline" hx-swap-oob="true">{timeline}</div>')
    resp['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'{amount:,.0f} FCFA encaissés ({len(allocations)} tranche(s) servie(s)).'.replace(',', ' '),
            'type': 'success',
            'receipt_url': reverse('payments:receipt', args=[payment.id]),
        },
        'close-collect-panel': {},
        # Permet à la page Paiements (lot 6) de rafraîchir sa liste + ses stats après
        # un encaissement. Ignoré ailleurs (la fiche élève se met à jour via l'OOB).
        'payment-collected': {},
    })
    return resp


# ── Remises (FeeAdjustment) — toute la logique argent est dans services.py ───────

def _render_discount_section(request, student, account):
    from .models import AdjustmentMotif, FundingSource
    return render(request, 'finance/partials/discount_section.html', {
        'student': student,
        'account': account,
        'debts': list(account.active_debts()) if account else [],
        'motifs': AdjustmentMotif.choices,
        'funding_sources': FundingSource.choices,
    })


@login_required
@director_or_staff_required
@require_http_methods(['GET'])
def discount_section(request, student_id):
    school = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school, is_active=True)
    return _render_discount_section(request, student, _active_account(student, school))


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def grant_discount(request, student_id):
    from decimal import Decimal, InvalidOperation
    from .services import create_fee_discount
    school = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school, is_active=True)
    account = _active_account(student, school)
    debt = _get_debt(student, school, request.POST.get('debt_id'))

    value_type = request.POST.get('value_type')          # 'percent' | 'amount'
    raw = (request.POST.get('value') or '').replace(' ', '').replace('%', '')
    try:
        percent = Decimal(raw) if value_type == 'percent' else None
        amount  = Decimal(raw) if value_type == 'amount'  else None
        create_fee_discount(
            debt,
            motif=request.POST.get('motif', 'other'),
            funding_source=request.POST.get('funding_source', 'school'),
            percent=percent, amount=amount,
            justification=(request.POST.get('justification') or '').strip(),
            created_by=request.user,
        )
    except (ValueError, InvalidOperation) as e:
        resp = _render_discount_section(request, student, account)
        return _toast(resp, str(e) or 'Valeur invalide.', 'error')

    resp = _render_discount_section(request, student, _active_account(student, school))
    return _toast(resp, 'Remise accordée.', 'success', **{'refresh-rail': True})


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def cancel_discount(request, student_id, adj_id):
    from .models import FeeAdjustment
    from .services import cancel_fee_discount
    school = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school, is_active=True)
    adj = get_object_or_404(
        FeeAdjustment, id=adj_id,
        debt__account__enrollment__student=student,
        debt__account__enrollment__school=school,
    )
    cancel_fee_discount(adj, cancelled_by=request.user)
    resp = _render_discount_section(request, student, _active_account(student, school))
    return _toast(resp, 'Remise annulée.', 'success', **{'refresh-rail': True})
