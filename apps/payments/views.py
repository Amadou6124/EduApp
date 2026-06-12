import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, F, Q, Subquery, OuterRef, Sum, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.schools.models import SchoolClass
from apps.core.mixins import get_school, director_or_staff_required
from apps.students.models import Student

from .forms import PaymentCancelForm, PaymentCreateForm
from .models import Payment


# ── Helpers ───────────────────────────────────────────────────────────────────



def _paid_subquery():
    return (
        Payment.objects
        .filter(student=OuterRef('pk'), is_cancelled=False)
        .values('student')
        .annotate(s=Sum('amount'))
        .values('s')
    )


def _students_qs(school):
    paid_sq = _paid_subquery()
    return (
        Student.objects
        .filter(school=school, is_active=True)
        .select_related('school_class')
        .annotate(
            total_paid=Coalesce(Subquery(paid_sq), Decimal('0'), output_field=DecimalField()),
            balance=ExpressionWrapper(
                F('tuition_fee') - Coalesce(Subquery(paid_sq), Decimal('0'), output_field=DecimalField()),
                output_field=DecimalField(),
            ),
        )
        .order_by('school_class__name', 'full_name')
    )


def _compute_stats(school, base_qs):
    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    encaisse_mois = (
        Payment.objects
        .filter(student__school=school, is_cancelled=False, payment_date__gte=first_of_month)
        .aggregate(s=Sum('amount'))['s'] or Decimal('0')
    )

    agg = base_qs.aggregate(
        total_due=Sum('tuition_fee'),
        total_paid_all=Sum('total_paid'),
        count_soldes=Count('id', filter=Q(balance__lte=0)),
        count_impayes=Count('id', filter=Q(total_paid=0)),
    )

    total_due = agg['total_due'] or Decimal('0')
    total_paid_all = agg['total_paid_all'] or Decimal('0')

    return {
        'total_due':      total_due,
        'encaisse_mois':  encaisse_mois,
        'solde_restant':  total_due - total_paid_all,
        'count_soldes':   agg['count_soldes'] or 0,
        'count_impayes':  agg['count_impayes'] or 0,
    }


def _apply_filters(qs, q, status, class_id):
    if q:
        qs = qs.filter(full_name__icontains=q)
    if class_id:
        qs = qs.filter(school_class_id=class_id)
    if status == 'unpaid':
        qs = qs.filter(total_paid=0)
    elif status == 'partial':
        qs = qs.filter(total_paid__gt=0, balance__gt=0)
    elif status == 'paid':
        qs = qs.filter(balance__lte=0)
    return qs


# ── Vues ──────────────────────────────────────────────────────────────────────

@login_required
def payment_dashboard(request):
    school = get_school(request)
    q        = request.GET.get('q', '').strip()
    status   = request.GET.get('status', 'unpaid')
    class_id = request.GET.get('class_id', '')

    base_qs  = _students_qs(school)
    stats    = _compute_stats(school, base_qs)
    filtered = _apply_filters(base_qs, q, status, class_id)

    classes = SchoolClass.objects.filter(school=school, is_active=True).order_by('name')

    tab_list = [
        ('all',     'Tous'),
        ('unpaid',  'Impayés'),
        ('partial', 'Partiel'),
        ('paid',    'Soldés'),
    ]

    ctx = {
        'students': filtered,
        'stats':    stats,
        'classes':  classes,
        'tab_list': tab_list,
        'q':        q,
        'status':   status,
        'class_id': class_id,
        'school':   school,
    }

    if request.htmx:
        return render(request, 'payments/partials/payment_list_refresh.html', ctx)

    return render(request, 'payments/dashboard.html', ctx)


@login_required
def payment_form(request, student_id):
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class').prefetch_related('payments'),
        id=student_id, school=school, is_active=True,
    )
    balance = student.get_balance_due()
    form    = PaymentCreateForm()
    return render(request, 'payments/partials/payment_form.html', {
        'student': student,
        'balance': balance,
        'form':    form,
    })


@login_required
@director_or_staff_required
@require_POST
def payment_create(request, student_id):
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class').prefetch_related('payments'),
        id=student_id, school=school, is_active=True,
    )
    form = PaymentCreateForm(request.POST, balance_due=student.get_balance_due())

    if form.is_valid():
        payment = form.save(commit=False)
        payment.student      = student
        payment.collected_by = request.user
        payment.save()

        balance_after = student.get_balance_due()

        # Re-fetch les stats + liste pour OOB
        base_qs  = _students_qs(school)
        stats    = _compute_stats(school, base_qs)

        resp = render(request, 'payments/partials/payment_create_success.html', {
            'payment':       payment,
            'student':       student,
            'balance_after': balance_after,
            'stats':         stats,
        })
        resp['HX-Trigger'] = json.dumps({
            'showToast': {
                'message': f'Versement de {payment.amount:,.0f} FCFA enregistré.',
                'type':    'success',
                'receipt_url': f'/payments/receipt/{payment.id}/',
            },
            'close-panel': True,
        })
        return resp

    balance = student.get_balance_due()
    return render(request, 'payments/partials/payment_form.html', {
        'student': student,
        'balance': balance,
        'form':    form,
    })


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
    return render(request, 'payments/partials/payment_timeline.html', {
        'student':    student,
        'payments':   payments,
        'total_paid': total_paid,
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
