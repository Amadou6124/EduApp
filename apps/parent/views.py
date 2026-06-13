"""
Vues Espace Parent — cross-école, lecture seule.
Données via request.user.guarded_students. Ne JAMAIS appeler get_school().
Sécurité : tout accès à un élève/bulletin est filtré par
guardians__guardian=request.user (la garde du parent).
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.mixins import parent_required


@login_required
@parent_required
def parent_dashboard(request):
    from apps.payments.models import Payment
    from apps.schools.models import Bulletin
    from apps.teachers.models import Attendance

    now = timezone.now()

    # 1 requête + 3 prefetch = zéro N+1 quel que soit le nombre d'enfants
    links = (
        request.user.guarded_students
        .select_related('student', 'student__school', 'student__school_class')
        .prefetch_related(
            Prefetch(
                'student__payments',
                queryset=Payment.objects.filter(is_cancelled=False).order_by('-payment_date'),
                to_attr='active_payments',
            ),
            Prefetch(
                'student__bulletins',
                queryset=Bulletin.objects
                    .filter(is_published=True, is_cancelled=False)
                    .select_related('period', 'period__school_year')
                    .order_by('-period__school_year__start_date', '-period__order'),
                to_attr='published_bulletins',
            ),
            Prefetch(
                'student__attendances',
                queryset=Attendance.objects.filter(
                    status='absent', date__year=now.year, date__month=now.month,
                ),
                to_attr='month_absences',
            ),
        )
        .order_by('-is_primary', 'student__full_name')
    )

    children = []
    for link in links:
        s = link.student
        total_paid = sum(p.amount for p in s.active_payments)
        balance = s.tuition_fee - total_paid
        status = 'paid' if balance <= 0 else ('partial' if total_paid > 0 else 'unpaid')
        pct = int(total_paid / s.tuition_fee * 100) if s.tuition_fee else 0
        bulletins = s.published_bulletins
        children.append({
            'student':        s,
            'relationship':   link.get_relationship_display(),
            'is_primary':     link.is_primary,
            'total_paid':     total_paid,
            'balance':        max(balance, 0),
            'pct_paid':       min(max(pct, 0), 100),
            'status':         status,
            'bulletins_count': len(bulletins),
            'last_bulletin':  bulletins[0] if bulletins else None,
            'absences_count': len(s.month_absences),
        })

    # Enfant actif : sélectionné (?child=) sinon le premier
    active_child_id = request.GET.get('child')
    active_child = None
    if active_child_id:
        active_child = next(
            (c for c in children if str(c['student'].id) == active_child_id), None
        )
    if not active_child and children:
        active_child = children[0]

    return render(request, 'parent/dashboard.html', {
        'children':     children,
        'active_child': active_child,
        'has_multiple': len(children) > 1,
    })


@login_required
@parent_required
def parent_bulletin_pdf(request, bulletin_id):
    """PDF d'un bulletin — seulement si le parent est tuteur de l'élève ET bulletin publié."""
    from apps.schools.models import Bulletin
    from apps.schools.services.bulletin_pdf import generate_bulletin_pdf

    bulletin = get_object_or_404(
        Bulletin,
        pk=bulletin_id,
        is_published=True,
        is_cancelled=False,
        student__guardians__guardian=request.user,
    )
    pdf_bytes = generate_bulletin_pdf(bulletin)
    filename = (
        f'bulletin_{bulletin.student.full_name.replace(" ", "_")}_'
        f'{bulletin.period.name.replace(" ", "_")}.pdf'
    )
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{filename}"'
    return resp
