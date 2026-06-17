"""
Vues Espace Parent — cross-école, lecture seule.
Données via request.user.guarded_students. Ne JAMAIS appeler get_school().
Sécurité : tout accès à un élève/bulletin est filtré par
guardians__guardian=request.user (la garde du parent).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.mixins import parent_required


@login_required
@parent_required
def parent_dashboard(request):
    from apps.payments.models import Payment
    from apps.schools.models import Bulletin
    from apps.teachers.models import Attendance, StudentObservation

    now = timezone.now()
    since_30 = now.date() - timedelta(days=30)

    # 1 requête + 4 prefetch = zéro N+1 quel que soit le nombre d'enfants
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
                queryset=Attendance.objects
                    .filter(status__in=['absent', 'late'], date__gte=since_30)
                    .order_by('-date'),
                to_attr='recent_absences',
            ),
            Prefetch(
                'student__observations',
                queryset=StudentObservation.objects
                    .filter(is_visible_to_parent=True)
                    .select_related('teacher')
                    .order_by('-created_at'),
                to_attr='shared_observations',
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
        lb = bulletins[0] if bulletins else None
        children.append({
            'student':        s,
            'relationship':   link.get_relationship_display(),
            'is_primary':     link.is_primary,
            'total_paid':     total_paid,
            'balance':        max(balance, 0),
            'pct_paid':       min(max(pct, 0), 100),
            'status':         status,
            'bulletins_count': len(bulletins),
            'last_bulletin':   lb,
            'last_bulletin_is_new': bool(
                lb and lb.published_at and
                (now.date() - lb.published_at.date()).days < 7
            ),
            'absences_count': len(s.recent_absences),
            'recent_absences': s.recent_absences,
            'observations':   s.shared_observations,
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
def parent_bulletins(request):
    """Tous les bulletins publiés des enfants du parent, groupés par enfant. Zéro N+1."""
    from apps.schools.models import Bulletin

    links = (
        request.user.guarded_students
        .select_related('student', 'student__school_class', 'student__school')
        .prefetch_related(Prefetch(
            'student__bulletins',
            queryset=Bulletin.objects
                .filter(is_published=True, is_cancelled=False)
                .select_related('period', 'period__school_year')
                .order_by('-period__school_year__start_date', '-period__order'),
            to_attr='published_bulletins',
        ))
        .order_by('-is_primary', 'student__full_name')
    )
    children = [{'student': l.student, 'bulletins': l.student.published_bulletins} for l in links]
    any_bulletins = any(c['bulletins'] for c in children)
    return render(request, 'parent/bulletins.html', {
        'children': children,
        'any_bulletins': any_bulletins,
    })


@login_required
@parent_required
def parent_payments(request):
    """Historique des paiements de tous les enfants + totaux. Zéro N+1."""
    from apps.payments.models import Payment

    links = (
        request.user.guarded_students
        .select_related('student', 'student__school_class')
        .prefetch_related(Prefetch(
            'student__payments',
            queryset=Payment.objects.filter(is_cancelled=False).order_by('-payment_date', '-created_at'),
            to_attr='active_payments',
        ))
        .order_by('-is_primary', 'student__full_name')
    )
    children = []
    total_paid_all = Decimal('0')
    total_due_all = Decimal('0')
    for l in links:
        s = l.student
        paid = sum((p.amount for p in s.active_payments), Decimal('0'))
        due = s.tuition_fee or Decimal('0')
        balance = max(due - paid, Decimal('0'))
        pct = int(paid / due * 100) if due else 0
        children.append({
            'student': s, 'payments': s.active_payments,
            'paid': paid, 'due': due, 'balance': balance,
            'pct': min(max(pct, 0), 100),
            'status': 'paid' if balance <= 0 else ('partial' if paid > 0 else 'unpaid'),
        })
        total_paid_all += paid
        total_due_all += due
    return render(request, 'parent/payments.html', {
        'children': children,
        'total_paid': total_paid_all,
        'total_remaining': max(total_due_all - total_paid_all, Decimal('0')),
    })


@login_required
@parent_required
def parent_account(request):
    """Profil parent + enfants liés."""
    links = (
        request.user.guarded_students
        .select_related('student', 'student__school', 'student__school_class')
        .order_by('-is_primary', 'student__full_name')
    )
    children = [{'student': l.student, 'relationship': l.get_relationship_display()} for l in links]
    return render(request, 'parent/account.html', {'children': children})


@login_required
@parent_required
def parent_notes(request):
    """Notes de l'enfant actif, groupées par période puis matière. Lecture seule."""
    from collections import OrderedDict
    from apps.schools.models import Note

    links = (
        request.user.guarded_students
        .select_related('student', 'student__school_class')
        .order_by('-is_primary', 'student__full_name')
    )
    children = [l.student for l in links]
    if not children:
        return render(request, 'parent/notes.html', {
            'children': [], 'active_student': None, 'periods_data': [],
        })

    active_id = request.GET.get('child')
    active_student = next((s for s in children if str(s.id) == active_id), None) or children[0]

    notes = (
        Note.objects
        .filter(student=active_student, is_cancelled=False)
        .select_related('class_subject__subject', 'period', 'period__school_year')
        .order_by('period__order', 'class_subject__order')
    )

    # Groupage : période → matière → notes
    grouped = OrderedDict()
    for n in notes:
        p = n.period
        subs = grouped.setdefault(p, OrderedDict())
        sid = n.class_subject.subject_id
        if sid not in subs:
            subs[sid] = {'subject': n.class_subject.subject, 'notes': []}
        subs[sid]['notes'].append(n)

    periods_data = []
    for period, subs in grouped.items():
        subjects = []
        for entry in subs.values():
            vals = [x.value for x in entry['notes']]
            moyenne = (sum(vals) / len(vals)) if vals else None
            subjects.append({
                'subject': entry['subject'], 'notes': entry['notes'], 'moyenne': moyenne,
            })
        periods_data.append({'period': period, 'subjects': subjects})

    return render(request, 'parent/notes.html', {
        'children': children,
        'active_student': active_student,
        'periods_data': periods_data,
    })


@login_required
@parent_required
def parent_notifications(request):
    """Liste des notifications du parent. Ordonné -created_at (Meta)."""
    from datetime import timedelta
    today     = timezone.now().date()
    yesterday = today - timedelta(days=1)
    week_ago  = today - timedelta(days=7)

    notifs = list(request.user.notifications.all())
    for n in notifs:
        d = n.created_at.date()
        if d == today:
            n.date_group = "Aujourd'hui"
        elif d == yesterday:
            n.date_group = "Hier"
        elif d >= week_ago:
            n.date_group = "Cette semaine"
        else:
            n.date_group = "Plus ancien"

    return render(request, 'parent/notifications.html', {
        'notifications': notifs,
        'unread_count': sum(1 for n in notifs if not n.is_read),
    })


@login_required
@parent_required
def notification_open(request, notif_id):
    """Marque lu puis redirige vers la cible de la notification."""
    from apps.notifications.models import Notification

    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
    return redirect(notif.url or 'parent:notifications')


@login_required
@parent_required
@require_http_methods(['POST'])
def notification_delete(request, notif_id):
    """Supprime une notification (réel). Renvoie vide → la card disparaît (swap)."""
    from apps.notifications.models import Notification

    get_object_or_404(Notification, id=notif_id, recipient=request.user).delete()
    return HttpResponse('')


@login_required
@parent_required
@require_http_methods(['POST'])
def notifications_read_all(request):
    """Marque toutes les notifications du parent comme lues."""
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('parent:notifications')


@login_required
@parent_required
@require_http_methods(['POST'])
def notifications_clear(request):
    """Supprime toutes les notifications du parent."""
    request.user.notifications.all().delete()
    return redirect('parent:notifications')


@login_required
@parent_required
def parent_bulletin_pdf(request, bulletin_id):
    """PDF d'un bulletin — seulement si le parent est tuteur de l'élève ET bulletin publié.
    ?download=1 → téléchargement (attachment), sinon affichage inline."""
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
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    return resp
