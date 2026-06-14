"""Vues Comptabilité — paie, dépenses, bilan (Phases 2-7)."""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.core.mixins import get_school, director_or_accounting_required


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
