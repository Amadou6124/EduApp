import json
from collections import defaultdict
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.mixins import get_school
from apps.schools.models import ClassSubject, Subject, SchoolClass
from apps.students.models import Student
from .models import User, UserRole, StaffPermission, Membership
from .team_forms import TeamMemberCreateForm, TeamMemberEditForm, StaffPermissionForm

# Libellés des profils prédéfinis exposés au template
_PRESETS = [
    ('Censeur',       'censeur'),
    ('Comptable',     'comptable'),
    ('Surveillant',   'surveillant'),
    ('Informaticien', 'informaticien'),
    ('Secrétaire',    'secretaire'),
]

# Permissions « toujours actives » exclues du décompte affiché.
_ALWAYS_ON_PERMS = {'can_view_students', 'can_view_classes'}


def _active_perm_count(perm):
    """Nombre de permissions explicitement activées (hors « toujours actif »)."""
    return sum(
        1 for f in perm._meta.fields
        if f.name.startswith('can_') and f.name not in _ALWAYS_ON_PERMS
        and getattr(perm, f.name)
    )


# ── Décorateur director uniquement ────────────────────────────────────────────

def director_required(view_func):
    """Réserve la vue au directeur et au superadmin. À placer après @login_required."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = reverse('accounts:login')
            return __import__('django.shortcuts', fromlist=['redirect']).redirect(
                f'{login_url}?next={request.path}'
            )
        if request.user.role != UserRole.DIRECTOR and not request.user.is_superuser:
            return HttpResponseForbidden(
                '<h1 style="font-family:sans-serif;padding:40px">'
                '403 — Accès réservé au directeur.</h1>'
            )
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Queryset helpers ──────────────────────────────────────────────────────────

def _teachers_qs(school):
    """
    Enseignants actifs avec leurs matières préchargées.
    Résout en 2 requêtes (User + ClassSubject) au lieu de N.
    """
    return (
        User.objects
        .filter(
            memberships__school=school,
            memberships__role=UserRole.TEACHER,
            memberships__is_active=True,
        )
        .prefetch_related(
            Prefetch(
                'teaching_subjects',
                queryset=(
                    ClassSubject.objects
                    .filter(is_active=True)
                    .select_related('subject', 'school_class')
                    .order_by('school_class__name', 'subject__name')
                ),
                to_attr='active_subjects',
            )
        )
        .order_by('full_name')
        .distinct()
    )


def _staff_qs(school):
    """
    Staff actif avec ses permissions préchargées.
    Résout en 2 requêtes (User + StaffPermission).
    """
    return (
        User.objects
        .filter(
            memberships__school=school,
            memberships__role=UserRole.STAFF,
            memberships__is_active=True,
        )
        .prefetch_related(
            Prefetch(
                'staff_permission',
                queryset=StaffPermission.objects.all(),
            )
        )
        .order_by('full_name')
        .distinct()
    )


def _inactive_qs(school):
    """Membres (enseignant/staff) désactivés dans cette école — Membership.is_active=False."""
    return (
        User.objects
        .filter(
            memberships__school=school,
            memberships__is_active=False,
            memberships__role__in=[UserRole.TEACHER, UserRole.STAFF],
        )
        .order_by('full_name')
        .distinct()
    )


# ── Vues ──────────────────────────────────────────────────────────────────────

@login_required
def team_list(request):
    """Annuaire unifié : directeur + staff + enseignants, recherche/filtre/pagination."""
    school = get_school(request)
    role_f = request.GET.get('role', 'all')
    q      = request.GET.get('q', '').strip()

    team_roles = [UserRole.DIRECTOR, UserRole.STAFF, UserRole.TEACHER]
    mqs = Membership.objects.filter(school=school, role__in=team_roles).select_related('user')
    if role_f == 'inactive':
        mqs = mqs.filter(is_active=False, role__in=[UserRole.TEACHER, UserRole.STAFF])
    else:
        mqs = mqs.filter(is_active=True)
        if role_f in (UserRole.TEACHER, UserRole.STAFF, UserRole.DIRECTOR):
            mqs = mqs.filter(role=role_f)
    if q:
        mqs = mqs.filter(Q(user__full_name__icontains=q) | Q(user__phone_number__icontains=q))
    mqs = mqs.order_by('user__full_name')

    page = Paginator(mqs, 30).get_page(request.GET.get('page'))
    memberships = list(page)

    # Enrichissement batch (zéro N+1) : matières/classes des profs, permissions du staff.
    teacher_ids = [m.user_id for m in memberships if m.role == UserRole.TEACHER]
    staff_ids   = [m.user_id for m in memberships if m.role == UserRole.STAFF]
    subj_by_teacher = defaultdict(list)
    cls_by_teacher  = defaultdict(set)
    if teacher_ids:
        for cs in (ClassSubject.objects
                   .filter(teacher_id__in=teacher_ids, is_active=True)
                   .select_related('subject', 'school_class')
                   .order_by('school_class__name', 'subject__name')):
            subj_by_teacher[cs.teacher_id].append(cs)
            cls_by_teacher[cs.teacher_id].add(cs.school_class_id)
    perms = ({p.user_id: p for p in StaffPermission.objects.filter(user_id__in=staff_ids)}
             if staff_ids else {})

    rows = [{
        'user':        m.user,
        'role':        m.role,
        'is_active':   m.is_active,
        'subjects':    subj_by_teacher.get(m.user_id, []),
        'class_count': len(cls_by_teacher.get(m.user_id, ())),
        'perm':        perms.get(m.user_id),
    } for m in memberships]

    base = Membership.objects.filter(school=school, is_active=True)
    t = base.filter(role=UserRole.TEACHER).count()
    s = base.filter(role=UserRole.STAFF).count()
    inactive_count = Membership.objects.filter(
        school=school, is_active=False, role__in=[UserRole.TEACHER, UserRole.STAFF],
    ).count()

    ctx = {
        'school':       school,
        'rows':         rows,
        'page_obj':     page,
        'role_filter':  role_f,
        'q':            q,
        'stats':        {'total': t + s, 'teachers': t, 'staff': s, 'inactive': inactive_count},
        'is_director':  request.user.role == UserRole.DIRECTOR or request.user.is_superuser,
        'perm_form':    StaffPermissionForm(),
        'presets':      _PRESETS,
    }
    if request.htmx:
        return render(request, 'team/partials/team_list_body.html', ctx)
    return render(request, 'team/team_list.html', ctx)


@login_required
@director_required
def team_member_create(request):
    school = get_school(request)

    if request.method != 'POST':
        return HttpResponse(status=405)

    # ── Branche LIAISON : rattacher un compte existant via Membership ──
    link_user_id = request.POST.get('link_user_id')
    if link_user_id:
        return _link_existing_member(request, school, link_user_id)

    # ── Branche CRÉATION : nouveau compte + Membership ──
    form = TeamMemberCreateForm(school, request.POST)
    if form.is_valid():
        user = form.save()                       # crée User + Membership
        # Le mot de passe posé par l'école est temporaire (affiché une seule fois) →
        # changement forcé à la 1re connexion (même discipline que les parents), sinon
        # il resterait éternel. Géré par ForcePasswordChangeMiddleware.
        user.must_change_password = True
        user.save(update_fields=['must_change_password'])
        role = form.cleaned_data['role']
        if role == UserRole.STAFF:
            membership = Membership.objects.filter(user=user, school=school).first()
            StaffPermission.objects.get_or_create(
                user=user, defaults={'membership': membership}
            )

        response = HttpResponse('')
        response['HX-Trigger'] = json.dumps({
            'close-panel': True,
            'team-changed': True,
            'team-member-added': {
                'phone_number': user.phone_number,
                'temp_pwd':     form.cleaned_data['password'],
                'user_id':      user.pk,
            },
        })
        return response

    # Formulaire invalide : renvoie les erreurs via toast (panel reste ouvert)
    errors = '; '.join(
        f'{f}: {e[0]}' for f, errs in form.errors.items()
        for e in [errs]
    )
    response = HttpResponse('', status=422)
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': errors or 'Vérifiez les champs.', 'type': 'error'},
    })
    return response


def _link_existing_member(request, school, link_user_id):
    """Rattache un User existant à l'école via Membership (réactive si désactivée)."""
    user = get_object_or_404(User, pk=link_user_id)
    role = request.POST.get('role', '')
    if role not in (UserRole.TEACHER, UserRole.STAFF):
        role = UserRole.TEACHER

    has_default = Membership.objects.filter(user=user, is_default=True).exists()
    membership, created = Membership.objects.get_or_create(
        user=user, school=school,
        defaults={
            'role':       role,
            'job_title':  user.job_title or '',
            'is_active':  True,
            'is_default': not has_default,
        },
    )
    if not created and not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=['is_active'])

    if role == UserRole.STAFF:
        StaffPermission.objects.get_or_create(
            user=user, defaults={'membership': membership}
        )
        # Staff lié → redirection vers sa fiche (l'éditeur de permissions y est).
        # Defaults : voir élèves + voir classes uniquement → à configurer.
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('team:detail', args=[user.pk]) + '?linked_staff=1'
        return response

    # Enseignant lié → ferme le panneau + rafraîchit la liste (pas de reload complet).
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({
        'close-panel': True,
        'team-changed': True,
        'showToast': {'message': f"{user.full_name} ajouté à l'équipe.", 'type': 'success'},
    })
    return response


@login_required
@director_required
def team_member_search(request):
    """Recherche un compte par téléphone : trouvé → carte de liaison ; sinon → form création."""
    school = get_school(request)
    phone = request.GET.get('phone', '').strip()

    # Contexte commun : le partial peut rendre le formulaire de création complet
    # (cas « numéro inconnu »), qui a besoin de perm_form + presets.
    ctx = {
        'school':    school,
        'phone':     phone,
        'perm_form': StaffPermissionForm(),
        'presets':   _PRESETS,
    }

    if not phone:
        ctx['searched'] = False
        return render(request, 'team/partials/member_search_result.html', ctx)

    user = User.objects.filter(phone_number=phone).first()
    ctx['searched']       = True
    ctx['found']          = user
    ctx['already_member'] = bool(
        user and Membership.objects.filter(
            user=user, school=school, is_active=True
        ).exists()
    )
    return render(request, 'team/partials/member_search_result.html', ctx)


@login_required
def team_member_detail(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, memberships__school=school)

    # Rôle CONTEXTUEL : celui de la Membership dans l'école courante, pas le
    # rôle global du User (un directeur d'une autre école peut être staff ici).
    membership  = Membership.objects.filter(user=member, school=school).first()
    member_role = membership.role if membership else member.role

    is_director = request.user.role == UserRole.DIRECTOR or request.user.is_superuser
    viewer_perm = getattr(request.user, 'staff_permission', None)
    context = {
        'school':                school,
        'member':                member,
        'member_role':           member_role,
        # Statut PER-ÉCOLE (Membership), pas le champ global User.is_active.
        'member_is_active':      membership.is_active if membership else member.is_active,
        'is_director':           is_director,
        'can_manage_accounting': is_director or bool(viewer_perm and viewer_perm.can_manage_accounting),
    }

    # Chiffres clés (divulgation progressive) — selon le rôle dans cette école.
    if member_role == UserRole.TEACHER:
        cs = ClassSubject.objects.filter(
            teacher=member, school_class__school=school, is_active=True,
        )
        class_ids = set(cs.values_list('school_class_id', flat=True))
        subj_ids  = set(cs.values_list('subject_id', flat=True))
        student_count = (
            Student.objects.filter(school_class_id__in=class_ids, is_active=True).count()
            if class_ids else 0
        )
        context['stats'] = {
            'classes':  len(class_ids),
            'subjects': len(subj_ids),
            'students': student_count,
        }
    elif member_role == UserRole.STAFF:
        perm, _ = StaffPermission.objects.get_or_create(user=member)
        context['perm']      = perm
        context['perm_form'] = StaffPermissionForm(instance=perm)
        context['stats'] = {'permissions': _active_perm_count(perm)}

    # « Fil vers la paie » : photo du mois COURANT sur la fiche du prof (lecture seule).
    if (member_role == UserRole.TEACHER and school.accounting_enabled
            and context['can_manage_accounting']):
        context['pay_month'] = _teacher_pay_month(school, member)

    return render(request, 'team/team_detail.html', context)


def _teacher_pay_month(school, member):
    """Photo paie du mois courant pour la fiche prof : heures émargées (les heures de
    REMPLAÇANT sont créditées — même règle que la paie), séances par statut, montant
    estimé (vacataire) ou salaire − retenue (permanent), bulletin s'il existe.
    Lecture seule : la vérité reste l'émargement + l'écran Salaires."""
    from datetime import date
    from apps.accounting.models import (
        TeacherAttendance, EmployeeProfile, EmploymentType, SalaryPayment,
    )
    from apps.accounting.services import (
        compute_teacher_hours, compute_vacataire_pay, compute_permanent_deductions,
    )

    today = date.today()
    y, m = today.year, today.month

    counts = {'present': 0, 'replaced': 0, 'absent': 0}
    for a in TeacherAttendance.objects.filter(
            school=school, teacher=member, date__year=y, date__month=m):
        counts[a.status] = counts.get(a.status, 0) + 1

    profile = EmployeeProfile.objects.filter(
        membership__user=member, membership__school=school,
    ).select_related('membership').first()

    info = {
        'ref':      date(y, m, 1),
        'hours':    compute_teacher_hours(school, y, m).get(member.id, 0),
        'counts':   counts,
        'profile':  profile,
        'is_vacataire': bool(profile and profile.employment_type == EmploymentType.VACATAIRE),
        'amount': None, 'unrated_hours': 0, 'deduction': None,
        'payment':  SalaryPayment.objects.filter(
            school=school, employee__user=member, year=y, month=m,
        ).first(),
    }
    if info['is_vacataire']:
        row = compute_vacataire_pay(school, y, m).get(member.id)
        if row:
            info['amount'], info['unrated_hours'] = row['amount'], row['unrated_hours']
    elif profile:
        info['deduction'] = compute_permanent_deductions(school, y, m).get(member.id)
    return info


@login_required
@director_required
def team_member_edit(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, memberships__school=school)

    if request.method == 'POST':
        form = TeamMemberEditForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            response['HX-Trigger'] = json.dumps({
                'close-edit-panel': True,
                'team-changed': True,
                'showToast': {'message': 'Fiche mise à jour.', 'type': 'success'},
                'team-member-updated': {'user_id': member.pk},
            })
            return response

        return render(request, 'team/partials/team_edit_form.html', {
            'school': school,
            'form':   form,
            'member': member,
        }, status=422)

    form = TeamMemberEditForm(instance=member)
    return render(request, 'team/partials/team_edit_form.html', {
        'school': school,
        'form':   form,
        'member': member,
    })


@login_required
@director_required
@require_POST
def team_permissions_update(request, user_id):
    school = get_school(request)
    member = get_object_or_404(
        User, pk=user_id,
        memberships__school=school, memberships__role=UserRole.STAFF,
    )
    perm, _ = StaffPermission.objects.get_or_create(user=member)

    form = StaffPermissionForm(request.POST, instance=perm)
    if form.is_valid():
        form.save()
        response = render(request, 'team/partials/staff_permissions.html', {
            'school':       school,
            'member':       member,
            'perm':         perm,
            'perm_form':    StaffPermissionForm(instance=perm),
            'is_director':  True,
            'active_count': _active_perm_count(perm),
        })
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Permissions mises à jour.', 'type': 'success'},
        })
        return response

    response = render(request, 'team/partials/staff_permissions.html', {
        'school':       school,
        'member':       member,
        'perm':         perm,
        'perm_form':    form,
        'is_director':  True,
        'active_count': _active_perm_count(perm),
    })
    response.status_code = 422
    return response


def _detail_header_response(request, school, member, message, toast_type):
    """Swap in-place de la carte identité (fiche détail) avec UN seul toast.

    Utilisé quand (dés)activation est déclenchée depuis la fiche détail
    (HX-Target=member-detail-header) → évite le full reload + le double toast.
    """
    membership = Membership.objects.filter(user=member, school=school).first()
    resp = render(request, 'team/partials/team_member_header.html', {
        'member':           member,
        'member_role':      membership.role if membership else member.role,
        'member_is_active': membership.is_active if membership else member.is_active,
        'is_director':      request.user.role == UserRole.DIRECTOR or request.user.is_superuser,
    })
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': toast_type}})
    return resp


def _from_detail_header(request):
    return request.headers.get('HX-Target') == 'member-detail-header'


@login_required
@director_required
@require_POST
def team_regenerate_password(request, user_id):
    """Régénère le mot de passe d'un membre (directeur uniquement) — débloque un membre
    qui a oublié le sien, en attendant l'auth par e-mail. Nouveau mdp temporaire affiché
    UNE fois + changement forcé re-armé (le temporaire meurt à la 1re connexion)."""
    from .team_forms import generate_temp_password
    school  = get_school(request)
    member  = get_object_or_404(User, pk=user_id, memberships__school=school)
    temp_pwd = generate_temp_password()
    member.set_password(temp_pwd)
    member.must_change_password = True
    member.save(update_fields=['password', 'must_change_password'])

    resp = HttpResponse('')
    # htmx émet nativement staff-credentials (kebab) → le modal écoute directement.
    resp['HX-Trigger'] = json.dumps({
        'staffCredentials': {
            'name':     member.full_name,
            'phone':    member.phone_number,
            'temp_pwd': temp_pwd,
        },
    })
    return resp


@login_required
@director_required
@require_POST
def team_member_deactivate(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, memberships__school=school)

    # Empêche l'auto-désactivation du directeur connecté
    if member.pk == request.user.pk:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Vous ne pouvez pas désactiver votre propre compte.', 'type': 'error'},
        })
        return resp

    # Désactivation PER-ÉCOLE : Membership.is_active=False (compte global intact).
    Membership.objects.filter(user=member, school=school).update(is_active=False)

    msg = f'{member.full_name} a été désactivé(e).'
    if _from_detail_header(request):
        return _detail_header_response(request, school, member, msg, 'info')

    resp = HttpResponse(status=204)
    resp['HX-Trigger'] = json.dumps({
        'team-changed': True,
        'showToast': {'message': msg, 'type': 'info'},
    })
    return resp


@login_required
@director_required
@require_POST
def team_member_reactivate(request, user_id):
    """Réactive un membre désactivé dans l'école courante (per-école, directeur).

    StaffPermission étant par-user, les permissions reviennent telles quelles.
    Recharge la page → le membre repasse dans la liste active.
    """
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, memberships__school=school)
    Membership.objects.filter(user=member, school=school).update(is_active=True)

    msg = f'{member.full_name} réactivé(e).'
    if _from_detail_header(request):
        return _detail_header_response(request, school, member, msg, 'success')

    response = HttpResponse(status=204)
    response['HX-Trigger'] = json.dumps({
        'team-changed': True,
        'showToast': {'message': msg, 'type': 'success'},
    })
    return response


def _teacher_subjects_ctx(school, member, saved=False):
    """Contexte commun pour le partial teacher_subjects.html."""
    all_class_subjects = (
        ClassSubject.objects
        .filter(school_class__school=school, is_active=True)
        .select_related('subject', 'school_class')
        .order_by('school_class__name', 'subject__name')
    )
    assigned_ids = set(
        ClassSubject.objects
        .filter(teacher=member)
        .values_list('id', flat=True)
    )
    classes = (
        SchoolClass.objects
        .filter(school=school, is_active=True)
        .order_by('level', 'name')
    )

    # Regroupement par classe (accordéon repliable) + décompte assigné/total.
    groups = []
    by_class = {}
    for cs in all_class_subjects:
        cs.assigned = cs.id in assigned_ids
        g = by_class.get(cs.school_class_id)
        if g is None:
            g = {'class': cs.school_class, 'subjects': [], 'assigned': 0, 'total': 0}
            by_class[cs.school_class_id] = g
            groups.append(g)
        g['subjects'].append(cs)
        g['total'] += 1
        if cs.assigned:
            g['assigned'] += 1

    return {
        'school':             school,
        'member':             member,
        'all_class_subjects': all_class_subjects,
        'assigned_ids':       assigned_ids,
        'groups':             groups,
        'classes':            classes,
        'is_director':        True,
        'saved':              saved,
    }


_ARABIC_KEYWORDS = ['arabe', 'fiqh', 'coran', 'hadith', 'tafsir', 'tarbiya']


@login_required
@director_required
def teacher_subjects_update(request, user_id):
    school = get_school(request)
    # Tout membre de l'école (pas seulement User.role=TEACHER) : la fiche affiche
    # la section « Matières » d'après le rôle d'APPARTENANCE (Membership), or un
    # directeur qui enseigne a User.role='director' → le filtre strict renvoyait un
    # 404 muet → « Chargement des matières… » figé pour toujours.
    # Appartenance à CETTE école (memberships__school), pas User.school (école
    # principale du compte) : un membre multi-école a User.school ailleurs → 404.
    member = get_object_or_404(User, pk=user_id, memberships__school=school)

    if request.method == 'POST':
        assigned_ids = set(
            ClassSubject.objects
            .filter(teacher=member)
            .values_list('id', flat=True)
        )
        selected_ids = set(int(i) for i in request.POST.getlist('class_subject_ids') if i.isdigit())

        to_assign   = selected_ids - assigned_ids
        to_unassign = assigned_ids - selected_ids

        if to_assign:
            ClassSubject.objects.filter(
                id__in=to_assign,
                school_class__school=school,
            ).update(teacher=member)

        if to_unassign:
            ClassSubject.objects.filter(
                id__in=to_unassign,
                teacher=member,
            ).update(teacher=None)

        ctx = _teacher_subjects_ctx(school, member, saved=True)
        response = render(request, 'team/partials/teacher_subjects.html', ctx)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Matières mises à jour.', 'type': 'success'},
        })
        return response

    return render(request, 'team/partials/teacher_subjects.html',
                  _teacher_subjects_ctx(school, member))


@login_required
@director_required
@require_POST
def teacher_assign_class(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, memberships__school=school)

    class_id     = request.POST.get('class_id', '').strip()
    filter_mode  = request.POST.get('filter', 'all')

    if not class_id:
        ctx = _teacher_subjects_ctx(school, member)
        response = render(request, 'team/partials/teacher_subjects.html', ctx)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Sélectionnez une classe.', 'type': 'error'},
        })
        return response

    school_class = get_object_or_404(
        SchoolClass, pk=class_id, school=school, is_active=True
    )

    arabic_q = Q()
    for kw in _ARABIC_KEYWORDS:
        arabic_q |= Q(subject__name__icontains=kw)
        arabic_q |= Q(subject__short_name__icontains=kw)

    qs = ClassSubject.objects.filter(school_class=school_class, is_active=True)
    if filter_mode == 'arabic':
        qs = qs.filter(arabic_q)
    elif filter_mode == 'french':
        qs = qs.exclude(arabic_q)

    count = qs.update(teacher=member)

    label = school_class.name
    msg   = f'{count} matière{"s" if count != 1 else ""} assignée{"s" if count != 1 else ""} en {label}.'

    ctx = _teacher_subjects_ctx(school, member, saved=True)
    response = render(request, 'team/partials/teacher_subjects.html', ctx)
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': msg, 'type': 'success'},
    })
    return response
