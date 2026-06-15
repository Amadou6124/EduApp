import json
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.mixins import get_school
from apps.schools.models import ClassSubject, Subject, SchoolClass
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


# ── Vues ──────────────────────────────────────────────────────────────────────

@login_required
def team_list(request):
    school   = get_school(request)
    teachers = _teachers_qs(school)
    staff    = _staff_qs(school)

    # Nombre de classes par enseignant (annotation distincte)
    teacher_class_counts = (
        ClassSubject.objects
        .filter(school_class__school=school, teacher__role=UserRole.TEACHER, is_active=True)
        .values('teacher_id')
        .annotate(class_count=Count('school_class', distinct=True))
    )
    counts_by_teacher = {row['teacher_id']: row['class_count'] for row in teacher_class_counts}

    # Enrichit chaque enseignant avec son nombre de classes (pas de N+1)
    teachers_data = [
        {'user': t, 'class_count': counts_by_teacher.get(t.pk, 0)}
        for t in teachers
    ]

    total_active = teachers.count() + staff.count()

    t = teachers.count()
    s = staff.count()
    return render(request, 'team/team_list.html', {
        'school':        school,
        'teachers_data': teachers_data,
        'staff_members': staff,
        'stats': {
            'total':    total_active,
            'teachers': t,
            'staff':    s,
        },
        'is_director':   request.user.role == UserRole.DIRECTOR or request.user.is_superuser,
        'perm_form':     StaffPermissionForm(),
        'presets':       _PRESETS,
        'page_subtitle': f"{t} enseignant{'s' if t != 1 else ''} · {s} staff",
    })


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
        role = form.cleaned_data['role']
        if role == UserRole.STAFF:
            membership = Membership.objects.filter(user=user, school=school).first()
            StaffPermission.objects.get_or_create(
                user=user, defaults={'membership': membership}
            )

        response = HttpResponse('')
        response['HX-Trigger'] = json.dumps({
            'close-panel': True,
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

    # Enseignant lié → retour liste avec toast (rien à configurer).
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': f"{user.full_name} ajouté à l'équipe.", 'type': 'success'},
    })
    response['HX-Refresh'] = 'true'
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
        'is_director':           is_director,
        'can_manage_accounting': is_director or bool(viewer_perm and viewer_perm.can_manage_accounting),
    }

    if member_role == UserRole.STAFF:
        perm, _ = StaffPermission.objects.get_or_create(user=member)
        context['perm']      = perm
        context['perm_form'] = StaffPermissionForm(instance=perm)

    return render(request, 'team/team_detail.html', context)


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
            'school':      school,
            'member':      member,
            'perm':        perm,
            'perm_form':   StaffPermissionForm(instance=perm),
            'is_director': True,
        })
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Permissions mises à jour.', 'type': 'success'},
        })
        return response

    response = render(request, 'team/partials/staff_permissions.html', {
        'school':      school,
        'member':      member,
        'perm':        perm,
        'perm_form':   form,
        'is_director': True,
    })
    response.status_code = 422
    return response


@login_required
@director_required
@require_POST
def team_member_deactivate(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, memberships__school=school)

    # Empêche l'auto-désactivation du directeur connecté
    if member.pk == request.user.pk:
        response = render(request, 'team/partials/member_card_refresh.html', {
            'school':      school,
            'member':      member,
            'is_director': True,
        })
        response['HX-Trigger'] = json.dumps({
            'showToast': {
                'message': 'Vous ne pouvez pas désactiver votre propre compte.',
                'type':    'error',
            },
        })
        return response

    # Désactivation PER-ÉCOLE : on retire le membre de l'école courante
    # (Membership.is_active=False) sans toucher au compte global ni à ses
    # rattachements dans d'autres écoles.
    Membership.objects.filter(user=member, school=school).update(is_active=False)

    response = render(request, 'team/partials/member_card_deactivated.html', {
        'school': school,
        'member': member,
    })
    response['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'{member.full_name} a été désactivé(e).',
            'type':    'info',
        },
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
    return {
        'school':             school,
        'member':             member,
        'all_class_subjects': all_class_subjects,
        'assigned_ids':       assigned_ids,
        'classes':            classes,
        'is_director':        True,
        'saved':              saved,
    }


_ARABIC_KEYWORDS = ['arabe', 'fiqh', 'coran', 'hadith', 'tafsir', 'tarbiya']


@login_required
@director_required
def teacher_subjects_update(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, school=school, role=UserRole.TEACHER)

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
    member = get_object_or_404(User, pk=user_id, school=school, role=UserRole.TEACHER)

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
