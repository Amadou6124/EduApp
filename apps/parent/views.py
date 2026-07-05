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
from apps.parent.children import resolve_active_child


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

    # ── Finances : NOUVEAU modèle (lot 6bis-B) via le helper central ────────────
    # student_fee_summary → 3 familles par allocation, identique à la fiche admin.
    # None = enfant sans fiche → état NEUTRE, jamais un solde faux.
    from apps.finance.services import student_fee_summary

    children = []
    for link in links:
        s = link.student
        summary = student_fee_summary(s)
        if summary:
            fin = {
                'has_fee':    True,
                'status':     summary['status'],          # paid / partial / unpaid
                'total_paid': summary['paid'],
                'balance':    summary['balance'],
                'due':        summary['due'],
                'has_overdue': summary['has_overdue'],
                'pct_paid':   int(summary['paid'] / summary['due'] * 100) if summary['due'] else 0,
            }
        else:
            fin = {'has_fee': False, 'status': 'no_fee', 'total_paid': 0,
                   'balance': 0, 'due': 0, 'has_overdue': False, 'pct_paid': 0}
        bulletins = s.published_bulletins
        lb = bulletins[0] if bulletins else None
        children.append({
            'student':        s,
            'relationship':   link.get_relationship_display(),
            'is_primary':     link.is_primary,
            **fin,
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

    # Enfant actif : persistant en session (source unique, cf. children.py)
    _active = resolve_active_child(request, [c['student'] for c in children])
    active_child = next(
        (c for c in children if _active and c['student'].id == _active.id), None
    )

    # ── Timeline détaillée de l'enfant ACTIF (lecture seule) ────────────────────
    # Sécurité : on part de active_child['student'], issu de guarded_students — JAMAIS
    # d'un id en paramètre. Préfetch debts→installments→allocations → zéro N+1 dans le
    # rendu de la timeline. fee_families = même structure 3 familles que la fiche admin.
    active_account = None
    active_fee_families = None
    if active_child and active_child['has_fee']:
        from apps.finance.models import StudentFeeAccount
        from apps.finance.services import timeline_families
        cs = active_child['student']
        active_account = (
            StudentFeeAccount.objects
            .filter(enrollment__student=cs, enrollment__status='active',
                    enrollment__school=cs.school)
            .select_related('enrollment__school_year')
            .prefetch_related('debts__installments__allocations')
            .order_by('-enrollment__school_year__start_date')
            .first()
        )
        active_fee_families = timeline_families(active_account)

    from apps.schools.models import SchoolAnnouncement
    from django.db.models import Q as _Q

    _school_ids  = list({c['student'].school_id for c in children})
    _class_ids   = [c['student'].school_class_id for c in children if c['student'].school_class_id]
    _student_ids = [c['student'].id for c in children]

    recent_announcements_count = SchoolAnnouncement.objects.filter(
        is_published=True
    ).filter(
        _Q(audience='school',  school_id__in=_school_ids) |
        _Q(audience='class',   target_class_id__in=_class_ids) |
        _Q(audience='student', target_student_id__in=_student_ids)
    ).count() if children else 0

    return render(request, 'parent/dashboard.html', {
        'children':                  children,
        'active_child':              active_child,
        'has_multiple':              len(children) > 1,
        'recent_announcements_count': recent_announcements_count,
        'active_account':            active_account,       # fiche de l'enfant actif (ou None)
        'active_fee_families':       active_fee_families,  # 3 familles pour la timeline
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
    # ── Solde : NOUVEAU modèle (lot 6bis-B) — IDENTIQUE à la fiche admin et à la
    # page Paiements. Le helper somme les allocations (3 familles), pas tuition_fee.
    # La liste des Payments bruts reste affichée comme JOURNAL des versements (immuable).
    from apps.finance.services import student_fee_summary

    children = []
    total_paid_all = Decimal('0')
    total_remaining_all = Decimal('0')
    for l in links:
        s = l.student
        for p in s.active_payments:
            p.month_group = p.payment_date.strftime('%Y-%m')
        summary = student_fee_summary(s)
        if summary:
            due     = Decimal(summary['due'])
            paid    = Decimal(summary['paid'])
            balance = Decimal(summary['balance'])
            status  = summary['status']
            has_fee = True
            pct     = int(paid / due * 100) if due else 0
        else:
            # Enfant sans fiche → état neutre, jamais un solde faux.
            due = paid = balance = Decimal('0')
            status, has_fee, pct = 'no_fee', False, 0
        children.append({
            'student': s, 'payments': s.active_payments, 'has_fee': has_fee,
            'paid': paid, 'due': due, 'balance': balance,
            'pct': min(max(pct, 0), 100), 'status': status,
        })
        total_paid_all += paid
        total_remaining_all += balance
    return render(request, 'parent/payments.html', {
        'children': children,
        'total_paid': total_paid_all,
        'total_remaining': total_remaining_all,
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

    active_student = resolve_active_child(request, children)

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
def parent_suivi(request):
    """Suivi scolaire : absences/retards, observations partagées, appréciations."""
    from datetime import date
    from apps.schools.models import SchoolYear, Bulletin
    from apps.teachers.models import Attendance, StudentObservation

    links = (
        request.user.guarded_students
        .select_related('student', 'student__school', 'student__school_class')
        .order_by('-is_primary', 'student__full_name')
    )
    children = [l.student for l in links]

    if not children:
        return render(request, 'parent/suivi.html', {
            'children': [], 'active_student': None,
            'attendances': [], 'observations': [], 'bulletins': [],
            'n_absent': 0, 'n_late': 0,
        })

    active_student = resolve_active_child(request, children)

    sy = SchoolYear.objects.filter(school=active_student.school, is_active=True).first()
    since = sy.start_date if sy else date.today().replace(month=9, day=1)

    attendances = (
        Attendance.objects
        .filter(student=active_student, status__in=['absent', 'late'], date__gte=since)
        .order_by('-date')
    )
    observations = (
        StudentObservation.objects
        .filter(student=active_student, is_visible_to_parent=True)
        .select_related('teacher')
        .order_by('-created_at')
    )
    bulletins = (
        Bulletin.objects
        .filter(student=active_student, is_published=True, is_cancelled=False)
        .select_related('period', 'period__school_year')
        .order_by('-period__school_year__start_date', '-period__order')
    )

    return render(request, 'parent/suivi.html', {
        'children': children,
        'active_student': active_student,
        'attendances': attendances,
        'observations': observations,
        'bulletins': bulletins,
        'n_absent': attendances.filter(status='absent').count(),
        'n_late': attendances.filter(status='late').count(),
    })


@login_required
@parent_required
def parent_annonces(request):
    """Annonces publiées des écoles des enfants du parent. Groupées par école si multi-école."""
    from collections import OrderedDict
    from django.db.models import Q
    from apps.schools.models import SchoolAnnouncement

    links = (
        request.user.guarded_students
        .select_related('student', 'student__school', 'student__school_class')
        .order_by('-is_primary', 'student__full_name')
    )
    student_ids = [l.student_id for l in links]
    class_ids   = [l.student.school_class_id for l in links if l.student.school_class_id]
    school_ids  = list({l.student.school_id for l in links})

    announcements = list(
        SchoolAnnouncement.objects
        .filter(is_published=True)
        .filter(
            Q(audience='school',  school_id__in=school_ids) |
            Q(audience='class',   target_class_id__in=class_ids) |
            Q(audience='student', target_student_id__in=student_ids)
        )
        .select_related('school', 'target_class', 'target_student', 'author')
        .order_by('-published_at')
    )

    # Ouvrir le fil = lire les annonces → marque les notifs liées comme lues
    # (sinon les accusés de lecture côté direction sous-comptent).
    ann_ids = [a.pk for a in announcements]
    if ann_ids:
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(SchoolAnnouncement)
        request.user.notifications.filter(
            content_type=ct, object_id__in=ann_ids, is_read=False,
        ).update(is_read=True)

    schools_map = OrderedDict()
    for ann in announcements:
        schools_map.setdefault(ann.school, []).append(ann)
    schools_map = OrderedDict(
        sorted(schools_map.items(), key=lambda x: x[0].name)
    )

    return render(request, 'parent/annonces.html', {
        'announcements':        announcements,
        'schools_map':          schools_map,
        'has_multiple_schools': len(schools_map) > 1,
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
