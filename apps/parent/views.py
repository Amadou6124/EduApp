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
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.mixins import parent_required
from apps.parent.children import parent_students, resolve_active_child


@login_required
@parent_required
def parent_dashboard(request):
    """Cockpit : fil « À votre attention » (signaux triés, tous enfants) + une
    carte de statut par enfant. Le détail vit dans les hubs Scolarité/Paiements."""
    from apps.schools.models import Bulletin, SchoolYear, SchoolAnnouncement
    from apps.teachers.models import Attendance
    from apps.teachers.services import student_attention_subjects
    from apps.finance.services import student_fee_summary
    from django.db.models import Q as _Q

    today = timezone.now().date()
    since_30 = today - timedelta(days=30)

    links = (
        request.user.guarded_students
        .select_related('student', 'student__school', 'student__school_class')
        .prefetch_related(
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
        )
        .order_by('-is_primary', 'student__full_name')
    )
    students = [l.student for l in links]
    active = resolve_active_child(request, students)

    # Période courante par école (cache) — pour le signal de suivi précoce.
    _pcache = {}
    def _cur_period(school):
        if school.id not in _pcache:
            sy = SchoolYear.objects.filter(school=school, is_active=True).first()
            per = None
            if sy:
                ps = list(sy.periods.order_by('order'))
                per = (next((p for p in ps if p.start_date <= today <= p.end_date), None)
                       or next((p for p in reversed(ps) if p.start_date <= today), None)
                       or (ps[0] if ps else None))
            _pcache[school.id] = per
        return _pcache[school.id]

    def _fmt(n):
        return f'{int(n):,}'.replace(',', ' ')

    child_cards, signals = [], []
    for s in students:
        summ = student_fee_summary(s)
        balance = Decimal(summ['balance']) if summ else None
        has_overdue = summ['has_overdue'] if summ else False
        lb = s.published_bulletins[0] if s.published_bulletins else None
        avg = lb.general_average if lb and lb.general_average is not None else None
        is_new_bulletin = bool(lb and lb.published_at and (today - lb.published_at.date()).days < 7)
        n_abs = sum(1 for a in s.recent_absences if a.status == 'absent')
        attention = student_attention_subjects(s, _cur_period(s.school))
        first = s.full_name.split()[0] if s.full_name else s.full_name

        child_cards.append({
            'student': s, 'has_fee': summ is not None, 'balance': balance,
            'has_overdue': has_overdue, 'average': avg, 'absences': n_abs,
            'active': bool(active and s.id == active.id),
        })

        if has_overdue and balance and balance > 0:
            signals.append({'urgency': 0, 'icon': 'alert-triangle', 'tone': 'danger',
                            'title': 'Paiement en retard', 'sub': f'{first} · {_fmt(balance)} FCFA',
                            'url': reverse('parent:payments') + f'?child={s.id}'})
        if attention:
            signals.append({'urgency': 1, 'icon': 'trending-down', 'tone': 'warn',
                            'title': "Point d'attention · " + ', '.join(attention[:2]),
                            'sub': f'{first} · un échange avec l\'enseignant peut aider',
                            'url': reverse('parent:scolarite') + f'?seg=notes&child={s.id}'})
        if n_abs >= 3:
            signals.append({'urgency': 1, 'icon': 'calendar-x', 'tone': 'danger',
                            'title': f'{n_abs} absences ce mois', 'sub': first,
                            'url': reverse('parent:scolarite') + f'?seg=assiduite&child={s.id}'})
        if is_new_bulletin:
            sub = first + (f' · {avg:.2f}/20'.replace('.', ',') if avg is not None else '')
            signals.append({'urgency': 2, 'icon': 'award', 'tone': 'indigo',
                            'title': f'Nouveau bulletin · {lb.period.name}', 'sub': sub,
                            'url': reverse('parent:scolarite') + f'?seg=bulletins&child={s.id}'})

    # Annonces (global, toutes écoles des enfants).
    if students:
        ann = SchoolAnnouncement.objects.filter(is_published=True).filter(
            _Q(audience='school',  school_id__in=list({s.school_id for s in students})) |
            _Q(audience='class',   target_class_id__in=[s.school_class_id for s in students if s.school_class_id]) |
            _Q(audience='student', target_student_id__in=[s.id for s in students])
        ).count()
        if ann:
            signals.append({'urgency': 3, 'icon': 'megaphone', 'tone': 'indigo',
                            'title': f'{ann} annonce{"s" if ann > 1 else ""} de l\'école',
                            'sub': 'Voir les annonces', 'url': reverse('parent:annonces')})

    signals.sort(key=lambda x: x['urgency'])

    return render(request, 'parent/dashboard.html', {
        'first_name':   request.user.full_name.split()[0] if request.user.full_name else '',
        'signals':      signals,
        'child_cards':  child_cards,
        'has_multiple': len(students) > 1,
    })


@login_required
@parent_required
def parent_bulletins(request):
    """Remplacée par le hub Scolarité (segment Bulletins). Redirection conservée
    pour les notifications et bookmarks dont l'URL est figée en base."""
    return redirect(reverse('parent:scolarite') + '?seg=bulletins')


@login_required
@parent_required
def parent_payments(request):
    """Paiements de l'enfant actif : solde, échéancier par famille (3 familles,
    tranches datées + retards — même logique que la fiche directeur via
    Installment.status/is_overdue) et journal des versements avec affectation.
    """
    from collections import OrderedDict
    from apps.payments.models import Payment
    from apps.finance.models import StudentFeeAccount
    from apps.finance.services import student_fee_summary, timeline_families

    students = parent_students(request.user)
    active = resolve_active_child(request, students)
    if not active:
        return render(request, 'parent/payments.html', {'active_student': None})

    # ── Vue d'ensemble « tous vos enfants », GROUPÉE PAR ÉCOLE ──────────────────
    # (on règle chaque école séparément). Affichée seulement si ≥2 enfants ont une
    # fiche. La fiche de l'enfant actif est réutilisée (pas de double calcul).
    summary = None
    overview_by_school = OrderedDict()
    fee_children = 0
    for st in students:
        summ = student_fee_summary(st) if st.id != active.id else None
        if st.id == active.id:
            summary = student_fee_summary(st)
            summ = summary
        if not summ:
            continue
        fee_children += 1
        entry = overview_by_school.setdefault(
            st.school, {'children': [], 'subtotal': Decimal('0'), 'has_overdue': False})
        entry['children'].append({
            'student': st, 'balance': summ['balance'],
            'has_overdue': summ['has_overdue'], 'active': st.id == active.id,
        })
        entry['subtotal'] += Decimal(summ['balance'])
        entry['has_overdue'] = entry['has_overdue'] or summ['has_overdue']
    fee_overview = list(overview_by_school.items()) if fee_children >= 2 else []
    account, fee_families = None, []
    overdue_total, overdue_count, pct_paid = Decimal('0'), 0, 0
    if summary:
        account = (
            StudentFeeAccount.objects
            .filter(pk=summary['account'].pk)
            .select_related('enrollment__school_year')
            .prefetch_related('debts__installments__allocations')
            .first()
        )
        fee_families = timeline_families(account)
        for _label, debts in fee_families:
            for debt in debts:
                for inst in debt.installments.all():
                    if inst.is_overdue():
                        overdue_total += inst.balance()
                        overdue_count += 1
        due = Decimal(summary['due'])
        pct_paid = min(max(int(Decimal(summary['paid']) / due * 100) if due else 0, 0), 100)

    # Journal des versements + affectation (PaymentAllocation → tranche → dette).
    payments = (
        Payment.objects
        .filter(student=active, is_cancelled=False)
        .prefetch_related('allocations__installment__debt')
        .order_by('-payment_date', '-created_at')
    )

    return render(request, 'parent/payments.html', {
        'active_student': active,
        'summary':        summary,
        'account':        account,
        'fee_families':   fee_families,
        'overdue_total':  overdue_total,
        'overdue_count':  overdue_count,
        'pct_paid':       pct_paid,
        'payments':       payments,
        'fee_overview':   fee_overview,
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
    """Remplacée par le hub Scolarité (segment Notes). Redirection conservée
    pour les notifications et bookmarks dont l'URL est figée en base."""
    return redirect(reverse('parent:scolarite') + '?seg=notes')


@login_required
@parent_required
def parent_suivi(request):
    """Remplacée par le hub Scolarité (segment Assiduité). Redirection conservée
    pour les notifications et bookmarks dont l'URL est figée en base."""
    return redirect(reverse('parent:scolarite') + '?seg=assiduite')


@login_required
@parent_required
def parent_scolarite(request):
    """Hub Scolarité — 3 segments (Notes · Assiduité · Bulletins) pour l'enfant actif.
    Notes : moyenne OFFICIELLE du bulletin si la période est publiée, sinon notes
    brutes marquées « non définitif ». Formatif publié = points d'étape hors bulletin.
    """
    from collections import OrderedDict, defaultdict
    from datetime import date
    from apps.schools.models import (
        Note, Bulletin, Period, SchoolYear, FormativeEvaluation, FormativeGrade,
    )
    from apps.teachers.models import Attendance, StudentObservation
    from apps.teachers.services import (
        compute_difficulty_score, LEVEL_CRITICAL, LEVEL_WARNING,
    )

    active = resolve_active_child(request, parent_students(request.user))
    if not active:
        return render(request, 'parent/scolarite.html', {'active_student': None})

    today = date.today()
    sy = SchoolYear.objects.filter(school=active.school, is_active=True).first()
    periods = list(Period.objects.filter(school_year=sy).order_by('order')) if sy else []

    # Période sélectionnée : ?period= sinon celle qui contient aujourd'hui, sinon la
    # dernière commencée, sinon la première.
    sel_id = request.GET.get('period')
    sel_period = next((p for p in periods if str(p.id) == sel_id), None)
    if not sel_period and periods:
        sel_period = (
            next((p for p in periods if p.start_date <= today <= p.end_date), None)
            or next((p for p in reversed(periods) if p.start_date <= today), None)
            or periods[0]
        )

    # ── NOTES (période sélectionnée) : officiel si bulletin publié, sinon brut ──
    subjects_rows, is_official, sel_bulletin = [], False, None
    attention_subjects = []   # matières « en difficulté » (période en cours seulement)
    if sel_period:
        sel_bulletin = (
            Bulletin.objects
            .filter(student=active, period=sel_period, is_published=True, is_cancelled=False)
            .prefetch_related('lines__class_subject__subject')
            .first()
        )
    if sel_bulletin:
        is_official = True
        for line in sel_bulletin.lines.all():
            subjects_rows.append({
                'subject':     line.class_subject.subject,
                'coefficient': line.class_subject.coefficient,
                'average':     line.final_average,
                'devoir':      line.devoir_average,
                'compo':       line.compo_grade,
            })
    elif sel_period:
        notes = list(
            Note.objects
            .filter(student=active, period=sel_period, is_cancelled=False)
            .select_related('class_subject', 'class_subject__subject')
        )
        by_sub, notes_by_cs = OrderedDict(), defaultdict(list)
        for n in notes:
            notes_by_cs[n.class_subject_id].append(n)
            sub = n.class_subject.subject
            row = by_sub.setdefault(sub.id, {
                'subject': sub, 'class_subject': n.class_subject,
                'coefficient': n.class_subject.coefficient,
                'devoir': None, 'compo': None,
            })
            if n.position == 2 or n.note_type == 'composition':
                row['compo'] = n.value
            else:
                row['devoir'] = n.value

        # Formatif de la période → alimente le signal de difficulté (garde-fou
        # anti-fausse-alerte dans compute_difficulty_score : < 2 données = non jugé).
        fg_by_cs = defaultdict(list)
        for v, mx, d, cs_id in (
            FormativeGrade.objects
            .filter(student=active, evaluation__period=sel_period,
                    is_absent=False, value__isnull=False)
            .values_list('value', 'evaluation__max_grade', 'evaluation__date',
                         'evaluation__class_subject')
        ):
            fg_by_cs[cs_id].append((v, mx, d))

        _soft_label = {LEVEL_CRITICAL: 'À renforcer', LEVEL_WARNING: 'À surveiller'}
        for row in by_sub.values():
            vals = [v for v in (row['devoir'], row['compo']) if v is not None]
            row['average'] = (sum(vals) / len(vals)) if vals else None
            diff = compute_difficulty_score(
                active, None, row['class_subject'], sel_period,
                notes_by_cs=notes_by_cs, fg_by_cs=fg_by_cs,
            )
            row['level'] = diff['level']
            row['level_label'] = _soft_label.get(diff['level'])
            row['trend'] = diff['trend']
            if diff['level'] == LEVEL_CRITICAL:
                attention_subjects.append(row['subject'].name)
            subjects_rows.append(row)

    # ── FORMATIF publié au parent (points d'étape, hors bulletin) ──
    formatif_rows = []
    if active.school_class_id:
        fevals = list(
            FormativeEvaluation.objects
            .filter(class_subject__school_class_id=active.school_class_id,
                    is_published_to_parent=True)
            .select_related('class_subject__subject')
            .order_by('-date')[:8]
        )
        fgrades = {
            g.evaluation_id: g
            for g in FormativeGrade.objects.filter(evaluation__in=fevals, student=active)
        }
        for f in fevals:
            formatif_rows.append({'eval': f, 'grade': fgrades.get(f.id)})

    # ── ASSIDUITÉ (année en cours) ──
    since = sy.start_date if sy else today.replace(month=9, day=1)
    attendances = list(
        Attendance.objects
        .filter(student=active, status__in=['absent', 'late'], date__gte=since)
        .order_by('-date')
    )
    n_absent = sum(1 for a in attendances if a.status == 'absent')
    n_late = sum(1 for a in attendances if a.status == 'late')
    observations = (
        StudentObservation.objects
        .filter(student=active, is_visible_to_parent=True)
        .select_related('teacher')
        .order_by('-created_at')
    )

    # ── BULLETINS publiés (liste, toutes périodes) ──
    bulletins = (
        Bulletin.objects
        .filter(student=active, is_published=True, is_cancelled=False)
        .select_related('period', 'period__school_year')
        .order_by('-period__school_year__start_date', '-period__order')
    )
    published_period_ids = {b.period_id for b in bulletins}

    return render(request, 'parent/scolarite.html', {
        'active_student':   active,
        'periods':          periods,
        'sel_period':       sel_period,
        'subjects_rows':    subjects_rows,
        'is_official':      is_official,
        'attention_subjects': attention_subjects,
        'formatif_rows':    formatif_rows,
        'n_absent':         n_absent,
        'n_late':           n_late,
        'attendances':      attendances,
        'observations':     observations,
        'bulletins':        bulletins,
        'published_period_ids': published_period_ids,
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
