import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, F, Prefetch, Q, Subquery, OuterRef, Sum
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRole

from apps.schools.models import SchoolClass
from apps.core.mixins import get_school, director_or_staff_required
from apps.students.models import Student

from .forms import PaymentCancelForm
from .models import Payment


# ── Helpers — NOUVEAU MODÈLE (lot 6) : tout part des StudentFeeAccount ───────────
# La page Paiements ne tourne PLUS sur l'ancien solde global (tuition_fee /
# get_total_paid). Elle agrège les 3 familles de dettes et leurs allocations :
#   - dû    = Σ FeeDebt.total_amount (dettes actives) de la fiche
#   - versé = Σ PaymentAllocation.amount affectées aux tranches de la fiche
#   - solde = dû − versé
# Calculé en sous-requêtes (pas de Sum multi-jointures qui multiplierait les lignes).

def _dashboard_accounts(school):
    """
    Fiches actives annotées dû/versé/solde + dernier paiement préchargé, pour la liste
    Paiements. S'appuie sur le helper CENTRAL `fee_accounts_annotated` (source unique
    partagée avec la liste élèves, le dashboard et le promoteur) ; on n'ajoute ici que
    le prefetch du dernier reçu et le tri d'affichage.
    """
    from apps.finance.services import fee_accounts_annotated
    return (
        fee_accounts_annotated(school=school)
        .prefetch_related(Prefetch(
            'enrollment__student__payments',
            queryset=Payment.objects.filter(is_cancelled=False).order_by('-payment_date'),
            to_attr='active_payments',
        ))
        .order_by('enrollment__student__school_class__name', 'enrollment__student__full_name')
    )


def _compute_stats(school, accounts):
    """Stats du haut — nouveau modèle. `accounts` = queryset annoté (toutes fiches)."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    # « Encaissé ce mois » = argent réellement reçu (journal Payment immuable), pas les
    # allocations : c'est la trésorerie entrée dans la caisse ce mois-ci.
    encaisse_mois = (
        Payment.objects
        .filter(student__school=school, is_cancelled=False, payment_date__gte=first_of_month)
        .aggregate(s=Sum('amount'))['s'] or Decimal('0')
    )

    agg = accounts.aggregate(
        total_due=Sum('due'),
        total_paid=Sum('paid'),
        count_soldes=Count('id', filter=Q(balance__lte=0)),
        count_impayes=Count('id', filter=Q(paid=0)),
    )
    total_due = agg['total_due'] or Decimal('0')
    total_paid = agg['total_paid'] or Decimal('0')

    # Élèves actifs SANS fiche financière (pas encore entrés par le nouveau système).
    # En prod (base vierge) = 0 ; en dev, on l'affiche à part pour ne pas fausser les
    # stats ni planter. Une fiche = 1 enrollment actif → on compte le delta.
    total_active = Student.objects.filter(school=school, is_active=True).count()
    sans_fiche = max(total_active - accounts.count(), 0)

    return {
        'total_due':     total_due,
        'encaisse_mois': encaisse_mois,
        'solde_restant': total_due - total_paid,
        'count_soldes':  agg['count_soldes'] or 0,
        'count_impayes': agg['count_impayes'] or 0,
        'sans_fiche':    sans_fiche,
    }


def _apply_filters(accounts, q, status, class_id):
    """Filtres recherche / classe / statut sur les fiches annotées."""
    if q:
        accounts = accounts.filter(enrollment__student__full_name__icontains=q)
    if class_id:
        accounts = accounts.filter(enrollment__student__school_class_id=class_id)
    if status == 'unpaid':            # rien versé
        accounts = accounts.filter(paid=0)
    elif status == 'partial':         # acompte < total
        accounts = accounts.filter(paid__gt=0, balance__gt=0)
    elif status == 'paid':            # soldé
        accounts = accounts.filter(balance__lte=0)
    return accounts


def _overdue_rows(school, q, class_id, today=None):
    """
    Liste rouge des impayés EN RETARD (lot 6) : élèves ayant ≥ 1 tranche dont
    due_date < aujourd'hui ET solde > 0. C'est l'aboutissement de la dimension
    temporelle (on exploite enfin Installment.due_date).

    Pour chaque élève : montant en retard (Σ des tranches échues impayées), nombre de
    tranches en retard, et ancienneté (jours depuis la plus vieille échéance dépassée).
    Tri par GRAVITÉ : le plus ancien retard d'abord (jours décroissants), puis le plus
    gros montant — le guichetier traite les cas les plus critiques en premier.
    """
    from apps.finance.models import Installment
    today = today or timezone.now().date()

    insts = (
        Installment.objects
        .filter(debt__account__enrollment__school=school,
                debt__account__enrollment__status='active',
                debt__account__enrollment__student__is_active=True,
                debt__is_active=True, due_date__lt=today)
        .annotate(allocated=Coalesce(Sum('allocations__amount'), Decimal('0')))
        .annotate(remaining=F('amount_due') - F('allocated'))
        .filter(remaining__gt=0)
        .select_related('debt__account__enrollment__student__school_class')
    )
    if class_id:
        insts = insts.filter(debt__account__enrollment__student__school_class_id=class_id)
    if q:
        insts = insts.filter(debt__account__enrollment__student__full_name__icontains=q)

    # Regroupement par élève (en Python : volume = élèves en retard, pas toute l'école).
    rows = {}
    for inst in insts:
        student = inst.debt.account.enrollment.student
        r = rows.get(student.id)
        if r is None:
            r = rows[student.id] = {
                'student': student, 'amount': Decimal('0'),
                'oldest': inst.due_date, 'count': 0,
            }
        r['amount'] += inst.remaining
        r['count'] += 1
        if inst.due_date < r['oldest']:
            r['oldest'] = inst.due_date
    out = list(rows.values())
    for r in out:
        r['days'] = (today - r['oldest']).days
    out.sort(key=lambda r: (-r['days'], -r['amount']))
    return out


def _annotate_reminders(school, rows, today=None):
    """Marque chaque ligne `reminded_today` = relance in-app déjà envoyée aujourd'hui."""
    from apps.notifications.models import Notification, NotificationCategory
    today = today or timezone.now().date()
    ids = [r['student'].id for r in rows]
    reminded = set(
        Notification.objects.filter(
            school=school, category=NotificationCategory.REMINDER,
            student_id__in=ids, created_at__date=today,
        ).values_list('student_id', flat=True)
    )
    for r in rows:
        r['reminded_today'] = r['student'].id in reminded


def _send_reminder(school, student):
    """Relance in-app aux parents (notif) si pas déjà fait aujourd'hui. True si envoyée."""
    from apps.notifications.models import Notification, NotificationCategory
    from apps.notifications.services import notify_guardians
    from apps.finance.services import student_fee_summary
    today = timezone.now().date()
    if Notification.objects.filter(
        school=school, category=NotificationCategory.REMINDER,
        student=student, created_at__date=today,
    ).exists():
        return False
    summ = student_fee_summary(student)
    balance = int(summ['balance']) if summ else 0
    body = f"Rappel : il reste {balance:,} FCFA à régler pour {student.full_name}.".replace(',', ' ')
    notify_guardians(
        student, category=NotificationCategory.REMINDER,
        title='Rappel de scolarité', body=body, url=reverse('parent:payments'),
    )
    return True


# ── Vues ──────────────────────────────────────────────────────────────────────

_TAB_LIST = [
    ('overdue', 'En retard'),   # 1er = onglet par défaut, visible d'emblée
    ('all',     'Tous'),
    ('unpaid',  'Impayés'),
    ('partial', 'Partiel'),
    ('paid',    'Soldés'),
]


@login_required
def payment_dashboard(request):
    if request.user.role == UserRole.TEACHER:
        return redirect('teacher:dashboard')
    school = get_school(request)
    q        = request.GET.get('q', '').strip()
    status   = request.GET.get('status', 'overdue')   # défaut : la liste rouge (relances)
    class_id = request.GET.get('class_id', '')

    accounts = _dashboard_accounts(school)
    stats    = _compute_stats(school, accounts)
    classes  = SchoolClass.objects.filter(school=school, is_active=True).order_by('name')

    ctx = {
        'stats':    stats,
        'classes':  classes,
        'tab_list': _TAB_LIST,
        'q':        q,
        'status':   status,
        'class_id': class_id,
        'school':   school,
    }

    ctx['is_overdue'] = (status == 'overdue')
    if ctx['is_overdue']:
        rows = _overdue_rows(school, q, class_id)
        _annotate_reminders(school, rows)
        page = Paginator(rows, 30).get_page(request.GET.get('page'))
        ctx['overdue_rows']      = page
        ctx['page_obj']          = page
        ctx['overdue_remindable'] = sum(1 for r in rows if not r['reminded_today'])
    else:
        page = Paginator(_apply_filters(accounts, q, status, class_id), 30).get_page(request.GET.get('page'))
        ctx['accounts'] = page
        ctx['page_obj'] = page

    if request.htmx:
        return render(request, 'payments/partials/payment_list_refresh.html', ctx)
    return render(request, 'payments/dashboard.html', ctx)


@login_required
@director_or_staff_required
@require_POST
def payment_remind(request, student_id):
    """Relance in-app (notif aux parents) pour 1 élève. Anti-spam : max 1/jour."""
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class'), id=student_id, school=school,
    )
    sent = _send_reminder(school, student)
    resp = render(request, 'payments/partials/remind_cell.html',
                  {'r': {'student': student, 'reminded_today': True}})
    resp['HX-Trigger'] = json.dumps({'showToast': {
        'message': 'Relance envoyée aux parents.' if sent else 'Déjà relancé aujourd\'hui.',
        'type': 'success' if sent else 'info',
    }})
    return resp


@login_required
@director_or_staff_required
@require_POST
def payment_remind_all(request):
    """Relance toutes les familles en retard du filtre courant (hors déjà relancées ce jour)."""
    school = get_school(request)
    q        = request.POST.get('q', '').strip()
    class_id = request.POST.get('class_id', '')
    rows = _overdue_rows(school, q, class_id)
    _annotate_reminders(school, rows)
    n = sum(1 for r in rows if not r['reminded_today'] and _send_reminder(school, r['student']))
    _annotate_reminders(school, rows)   # rafraîchit l'état post-envoi
    page = Paginator(rows, 30).get_page(1)
    ctx = {
        'overdue_rows': page, 'page_obj': page, 'is_overdue': True,
        'overdue_remindable': 0, 'q': q, 'class_id': class_id, 'status': 'overdue',
        'stats': _compute_stats(school, _dashboard_accounts(school)),
    }
    resp = render(request, 'payments/partials/payment_list_refresh.html', ctx)
    resp['HX-Trigger'] = json.dumps({'showToast': {
        'message': f'{n} famille(s) relancée(s).' if n else 'Toutes déjà relancées aujourd\'hui.',
        'type': 'success' if n else 'info',
    }})
    return resp


@login_required
def payment_history(request, student_id):
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class'),
        id=student_id, school=school, is_active=True,
    )
    payments = (
        Payment.objects
        .filter(student=student)
        .select_related('collected_by')
        .order_by('-payment_date', '-created_at')
    )
    total_paid = sum(p.amount for p in payments if not p.is_cancelled)

    # ── Tuiles de solde : NOUVEAU modèle (lot 6 finition) ───────────────────────
    # On affiche dû/versé/solde des 3 familles par allocation (comme la page Paiements
    # et la timeline fiche), pas l'ancien tuition_fee scolarité-seule. None si l'élève
    # n'a pas encore de fiche (dev / base partielle) → la modale montre un état neutre.
    from apps.finance.models import StudentFeeAccount
    fee_account = (
        StudentFeeAccount.objects
        .filter(enrollment__student=student, enrollment__status='active',
                enrollment__school=school)
        .prefetch_related('debts__installments__allocations')
        .order_by('-enrollment__school_year__start_date')
        .first()
    )
    return render(request, 'payments/partials/payment_timeline.html', {
        'student':     student,
        'payments':    payments,
        'total_paid':  total_paid,
        'fee_account': fee_account,
    })


@login_required
@director_or_staff_required
@require_POST
def payment_cancel(request, payment_id):
    school = get_school(request)
    payment = get_object_or_404(
        Payment.objects.select_related('student__school_class'),
        id=payment_id, student__school=school, is_cancelled=False,
    )
    form = PaymentCancelForm(request.POST, instance=payment)
    if form.is_valid():
        p = form.save(commit=False)
        p.is_cancelled = True
        p.cancelled_at = timezone.now()
        p.save()

        student  = payment.student
        payments = (
            Payment.objects
            .filter(student=student)
            .select_related('collected_by')
            .order_by('-payment_date', '-created_at')
        )
        total_paid = sum(p2.amount for p2 in payments if not p2.is_cancelled)
        resp = render(request, 'payments/partials/payment_timeline.html', {
            'student':    student,
            'payments':   payments,
            'total_paid': total_paid,
        })
        resp['HX-Trigger'] = json.dumps(
            {'showToast': {'message': 'Paiement annulé.', 'type': 'info'}}
        )
        return resp

    return HttpResponse(status=400)


@login_required
def receipt_preview(request, payment_id):
    school  = get_school(request)
    payment = get_object_or_404(
        Payment.objects.select_related('student__school_class'),
        id=payment_id, student__school=school, is_cancelled=False,
    )
    return render(request, 'payments/partials/receipt_preview_panel.html', {
        'payment':      payment,
        'receipt_url':  reverse('payments:receipt',          args=[payment_id]),
        'download_url': reverse('payments:receipt-download', args=[payment_id]),
    })


@login_required
def receipt_download(request, payment_id):
    school  = get_school(request)
    payment = get_object_or_404(
        Payment.objects.select_related('student__school_class'),
        id=payment_id, student__school=school, is_cancelled=False,
    )
    from .services.receipt_generator import generate_receipt
    try:
        pdf_bytes = generate_receipt(payment, school)
    except Exception as exc:
        return HttpResponse(f'Erreur génération PDF : {exc}', status=500, content_type='text/plain')

    safe_name = payment.student.full_name.replace(' ', '_')
    filename  = f'recu_{safe_name}_{payment.receipt_number}.pdf'
    response  = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@xframe_options_sameorigin
def payment_receipt_download(request, payment_id):
    school = get_school(request)
    payment = get_object_or_404(
        Payment.objects.select_related('student__school_class'),
        id=payment_id, student__school=school, is_cancelled=False,
    )
    from .services.receipt_generator import generate_receipt
    try:
        pdf_bytes = generate_receipt(payment, school)
    except Exception as exc:
        return HttpResponse(f'Erreur génération PDF : {exc}', status=500, content_type='text/plain')

    safe_name = payment.student.full_name.replace(' ', '_')
    filename  = f'recu_{safe_name}_{payment.receipt_number}.pdf'
    response  = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
