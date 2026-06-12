import json
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.mixins import get_school
from apps.schools.models import ClassSubject
from .models import User, UserRole, StaffPermission
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
        .filter(school=school, role=UserRole.TEACHER, is_active=True)
        .prefetch_related(
            Prefetch(
                'class_subjects',
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
    )


def _staff_qs(school):
    """
    Staff actif avec ses permissions préchargées.
    Résout en 2 requêtes (User + StaffPermission).
    """
    return (
        User.objects
        .filter(school=school, role=UserRole.STAFF, is_active=True)
        .prefetch_related(
            Prefetch(
                'staff_permission',
                queryset=StaffPermission.objects.all(),
            )
        )
        .order_by('full_name')
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
        .filter(teacher__school=school, teacher__role=UserRole.TEACHER, is_active=True)
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

    return render(request, 'team/team_list.html', {
        'teachers_data': teachers_data,
        'staff_members': staff,
        'stats': {
            'total':    total_active,
            'teachers': teachers.count(),
            'staff':    staff.count(),
        },
        'is_director': request.user.role == UserRole.DIRECTOR or request.user.is_superuser,
        # Formulaire permissions vide — utilisé dans le panel création staff
        'perm_form': StaffPermissionForm(),
        'presets':   _PRESETS,
    })


@login_required
@director_required
def team_member_create(request):
    school = get_school(request)

    if request.method == 'POST':
        form = TeamMemberCreateForm(school, request.POST)
        if form.is_valid():
            user      = form.save()
            role      = form.cleaned_data['role']
            temp_pwd  = form.cleaned_data['password']

            # Crée les permissions par défaut si staff
            if role == UserRole.STAFF:
                StaffPermission.objects.get_or_create(user=user)

                from django.http import HttpResponse
            response = HttpResponse('')
            response['HX-Trigger'] = json.dumps({
                'close-panel': True,
                'team-member-added': {
                    'phone_number': user.phone_number,
                    'temp_pwd':     temp_pwd,
                    'user_id':      user.pk,
                },
            })
            return response

        # Formulaire invalide : renvoie les erreurs via toast (panel reste ouvert)
        errors = '; '.join(
            f'{f}: {e[0]}' for f, errs in form.errors.items()
            for e in [errs]
        )
        from django.http import HttpResponse
        response = HttpResponse('', status=422)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': errors or 'Vérifiez les champs.', 'type': 'error'},
        })
        return response


@login_required
def team_member_detail(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, school=school)

    context = {
        'member':     member,
        'is_director': request.user.role == UserRole.DIRECTOR or request.user.is_superuser,
    }

    if member.role == UserRole.TEACHER:
        context['subjects'] = (
            ClassSubject.objects
            .filter(teacher=member, is_active=True)
            .select_related('subject', 'school_class')
            .order_by('school_class__name', 'subject__name')
        )

    if member.role == UserRole.STAFF:
        perm, _ = StaffPermission.objects.get_or_create(user=member)
        context['perm']      = perm
        context['perm_form'] = StaffPermissionForm(instance=perm)

    return render(request, 'team/team_detail.html', context)


@login_required
@director_required
def team_member_edit(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, school=school)

    if request.method == 'POST':
        form = TeamMemberEditForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            from django.http import HttpResponse
            response = HttpResponse('')
            response['HX-Trigger'] = json.dumps({
                'close-edit-panel': True,
                'showToast': {'message': 'Fiche mise à jour.', 'type': 'success'},
                'team-member-updated': {'user_id': member.pk},
            })
            return response

        return render(request, 'team/partials/team_edit_form.html', {
            'form':   form,
            'member': member,
        }, status=422)

    form = TeamMemberEditForm(instance=member)
    return render(request, 'team/partials/team_edit_form.html', {
        'form':   form,
        'member': member,
    })


@login_required
@director_required
@require_POST
def team_permissions_update(request, user_id):
    school = get_school(request)
    member = get_object_or_404(User, pk=user_id, school=school, role=UserRole.STAFF)
    perm, _ = StaffPermission.objects.get_or_create(user=member)

    form = StaffPermissionForm(request.POST, instance=perm)
    if form.is_valid():
        form.save()
        response = render(request, 'team/partials/staff_permissions.html', {
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
    member = get_object_or_404(User, pk=user_id, school=school)

    # Empêche l'auto-désactivation du directeur connecté
    if member.pk == request.user.pk:
        response = render(request, 'team/partials/member_card_refresh.html', {
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

    member.is_active = False
    member.save(update_fields=['is_active'])

    response = render(request, 'team/partials/member_card_deactivated.html', {
        'member': member,
    })
    response['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'{member.full_name} a été désactivé(e).',
            'type':    'info',
        },
    })
    return response
