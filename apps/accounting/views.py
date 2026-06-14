"""Vues Comptabilité — paie, dépenses, bilan (Phases 2-7)."""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.core.mixins import (
    get_school, director_or_accounting_required, director_or_emargement_required,
)


def _toast_error(message):
    resp = HttpResponse(status=422)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': 'error'}})
    return resp


def _parse_money(raw):
    raw = (raw or '').strip().replace(' ', '')
    if not raw:
        return None
    try:
        v = Decimal(raw)
    except InvalidOperation:
        return None
    return v if v >= 0 else None


# ─── Phase 2 — Liste employés & rémunération ─────────────────────────────────

@login_required
@director_or_accounting_required
def accounting_staff_list(request):
    """Liste des membres payables de l'école + leur profil de rémunération. Zéro N+1."""
    from apps.accounts.models import Membership

    school = get_school(request)
    if not school.accounting_enabled:
        return HttpResponse(status=403)

    memberships = (
        Membership.objects
        .filter(school=school, is_active=True)
        .exclude(role__in=['parent', 'student'])
        .select_related('user', 'employee_profile')   # reverse OneToOne → 1 requête
        .order_by('role', 'user__full_name')
    )

    items = []
    counts = {'all': 0, 'permanent': 0, 'vacataire': 0, 'none': 0}
    for m in memberships:
        profile = getattr(m, 'employee_profile', None)   # RelatedObjectDoesNotExist ⊂ AttributeError → None
        if profile is None:
            cat = 'none'
        elif profile.employment_type == 'permanent':
            cat = 'permanent'
        else:
            cat = 'vacataire'
        items.append({'membership': m, 'profile': profile, 'cat': cat})
        counts['all'] += 1
        counts[cat] += 1

    return render(request, 'accounting/staff_list.html', {
        'items': items, 'counts': counts, 'school': school,
        'no_profile_count': counts['none'],
    })


# ─── Phase 2 — Rémunération employé (panneau lazy-load dans /team/<id>/) ──────

@login_required
@director_or_accounting_required
def employee_remuneration_panel(request, user_id):
    """Panneau rémunération (GET, lazy-load HTMX). 403 si module désactivé."""
    from apps.accounts.models import User, Membership
    from .models import EmployeeProfile, EmploymentType

    school = get_school(request)
    if not school.accounting_enabled:
        return HttpResponse(status=403)

    member = get_object_or_404(User, pk=user_id, school=school)
    membership = get_object_or_404(Membership, user=member, school=school)
    profile, _ = EmployeeProfile.objects.get_or_create(
        membership=membership,
        defaults={'employment_type': EmploymentType.PERMANENT},
    )
    return render(request, 'accounting/partials/employee_remuneration.html', {
        'member': member, 'profile': profile, 'school': school,
    })


@login_required
@director_or_accounting_required
@require_http_methods(['POST'])
def employee_remuneration_save(request, user_id):
    """Sauvegarde EmployeeProfile. Permanent → salaire requis ; vacataire → taux requis."""
    from apps.accounts.models import User, Membership
    from .models import EmployeeProfile, EmploymentType

    school = get_school(request)
    if not school.accounting_enabled:
        return HttpResponse(status=403)

    member = get_object_or_404(User, pk=user_id, school=school)
    membership = get_object_or_404(Membership, user=member, school=school)
    profile, _ = EmployeeProfile.objects.get_or_create(membership=membership)

    emp_type = request.POST.get('employment_type', 'permanent')
    if emp_type not in (EmploymentType.PERMANENT, EmploymentType.VACATAIRE):
        emp_type = EmploymentType.PERMANENT

    monthly = _parse_money(request.POST.get('monthly_salary'))
    hourly  = _parse_money(request.POST.get('hourly_rate'))

    if emp_type == EmploymentType.PERMANENT and monthly is None:
        return _toast_error('Le salaire mensuel est obligatoire pour un permanent.')
    if emp_type == EmploymentType.VACATAIRE and hourly is None:
        return _toast_error('Le taux horaire est obligatoire pour un vacataire.')

    hire_raw = (request.POST.get('hire_date') or '').strip()
    hire_date = None
    if hire_raw:
        try:
            hire_date = datetime.strptime(hire_raw, '%Y-%m-%d').date()
        except ValueError:
            hire_date = None

    profile.employment_type = emp_type
    profile.monthly_salary = monthly if emp_type == EmploymentType.PERMANENT else None
    profile.hourly_rate    = hourly if emp_type == EmploymentType.VACATAIRE else None
    profile.hire_date = hire_date
    profile.save()

    resp = render(request, 'accounting/partials/employee_remuneration.html', {
        'member': member, 'profile': profile, 'school': school,
    })
    resp['HX-Trigger'] = json.dumps({
        'showToast': {'message': 'Rémunération enregistrée.', 'type': 'success'},
    })
    return resp


# ─── Phase 3 — Émargement enseignants ────────────────────────────────────────

_LEVEL_BADGE = {
    'prescolaire':    'bg-purple-100 text-purple-700',
    'fondamental_1':  'bg-blue-100 text-blue-700',
    'fondamental_2':  'bg-indigo-100 text-indigo-700',
    'secondaire_gen': 'bg-green-100 text-green-700',
    'secondaire_pro': 'bg-teal-100 text-teal-700',
    'superieur':      'bg-orange-100 text-orange-700',
}
_SESSIONS = ['morning', 'afternoon', 'full']


@login_required
@director_or_emargement_required
def emargement_dashboard(request):
    """Émargement du jour, cours groupés par classe. 3 requêtes, zéro N+1."""
    from datetime import datetime as _dt, date as _date, timedelta
    from collections import OrderedDict
    from apps.schools.models import ClassSubject
    from .models import TeacherAttendance

    school = get_school(request)
    if not school.accounting_enabled:
        return HttpResponse(status=403)

    today = _date.today()
    try:
        selected_date = _dt.strptime(request.GET.get('date', ''), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = today

    cs_list = (
        ClassSubject.objects
        .filter(school_class__school=school, school_class__is_active=True,
                is_active=True, teacher__isnull=False)
        .select_related('subject', 'teacher', 'school_class')
        .order_by('school_class__level', 'school_class__name', 'order', 'subject__name')
    )
    att_map = {
        (a.class_subject_id, a.session): a
        for a in TeacherAttendance.objects.filter(school=school, date=selected_date).select_related('substitute')
    }

    by_class = OrderedDict()
    init_state = {}
    for cs in cs_list:
        by_class.setdefault(cs.school_class_id, {'sc': cs.school_class, 'courses': []})
        sessions = {}
        for s in _SESSIONS:
            a = att_map.get((cs.id, s))
            sessions[s] = {
                'status':   a.status if a else '',
                'sub_id':   str(a.substitute_id) if a and a.substitute_id else '',
                'sub_name': a.substitute.full_name if a and a.substitute else '',
            }
        init_state[str(cs.id)] = sessions
        by_class[cs.school_class_id]['courses'].append({
            'cs': cs,
            'is_self': cs.teacher_id == request.user.id,   # anti-fraude UI
        })

    classes_data = [{
        'school_class': e['sc'], 'courses': e['courses'], 'total': len(e['courses']),
        'level_badge': _LEVEL_BADGE.get(e['sc'].level, 'bg-gray-100 text-gray-600'),
        'course_ids': [c['cs'].id for c in e['courses']],
    } for e in by_class.values()]

    return render(request, 'accounting/emargement.html', {
        'school': school,
        'selected_date': selected_date,
        'today': today,
        'prev_date': selected_date - timedelta(days=1),
        'next_date': selected_date + timedelta(days=1),
        'classes_data': classes_data,
        'total_courses': sum(c['total'] for c in classes_data),
        'init_state': init_state,
    })


@login_required
@director_or_emargement_required
@require_http_methods(['POST'])
def emargement_save(request):
    """Persiste un émargement (Alpine gère l'UI → 204). Anti-fraude : user ≠ teacher du cours."""
    from datetime import datetime as _dt
    from apps.schools.models import ClassSubject
    from apps.accounts.models import User
    from .models import TeacherAttendance, SessionType, TeacherAttendanceStatus

    school = get_school(request)
    if not school.accounting_enabled:
        return HttpResponse(status=403)

    try:
        cs_id = int(request.POST.get('class_subject_id'))
    except (TypeError, ValueError):
        return HttpResponse(status=400)
    cs = get_object_or_404(
        ClassSubject, pk=cs_id, school_class__school=school, is_active=True, teacher__isnull=False,
    )

    # Anti-fraude : un enseignant ne peut pas émarger son propre cours
    if cs.teacher_id == request.user.id:
        return _toast_error("Vous ne pouvez pas émarger votre propre cours.")

    try:
        d = _dt.strptime(request.POST.get('date', ''), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return HttpResponse(status=400)

    session = request.POST.get('session', 'morning')
    if session not in {c[0] for c in SessionType.choices}:
        session = 'morning'
    status = request.POST.get('status', '')
    if status not in {c[0] for c in TeacherAttendanceStatus.choices}:
        return HttpResponse(status=400)

    substitute = None
    if status == 'replaced':
        sub_id = request.POST.get('substitute_id')
        if sub_id:
            substitute = User.objects.filter(
                pk=sub_id, memberships__school=school, memberships__role='teacher',
            ).first()

    TeacherAttendance.objects.update_or_create(
        class_subject=cs, date=d, session=session,
        defaults={
            'teacher': cs.teacher, 'school': school, 'status': status,
            'substitute': substitute, 'recorded_by': request.user,
            'note': request.POST.get('note', '').strip()[:200],
        },
    )
    return HttpResponse(status=204)


@login_required
@director_or_emargement_required
def emargement_substitute_search(request):
    """Recherche d'un remplaçant (enseignant de l'école)."""
    from apps.accounts.models import User

    school = get_school(request)
    q  = request.GET.get('q', '').strip()
    cs = request.GET.get('cs', '')
    results = []
    if len(q) >= 2:
        results = list(
            User.objects
            .filter(memberships__school=school, memberships__role='teacher',
                    full_name__icontains=q, is_active=True)
            .distinct().order_by('full_name')[:8]
        )
    return render(request, 'accounting/partials/substitute_results.html', {'results': results, 'cs': cs})
