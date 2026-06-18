import secrets
from functools import wraps

from django.contrib import messages
from django.db.models import Count, Q, Sum, Prefetch
from django.db.models.functions import TruncMonth
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SchoolClass, SchoolGroup
from apps.students.models import Student
from apps.payments.models import Payment
from apps.lessons.models import Lesson

from .models import User, UserRole
from .superadmin_forms import (
    SchoolCreateForm, SchoolUpdateForm,
    DirectorCreateForm, DirectorUpdateForm, UserCreateForm,
)


def superadmin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = reverse('accounts:login')
            return redirect(f'{login_url}?next={request.path}')
        if not request.user.is_superuser:
            return HttpResponseForbidden(
                '<h1 style="font-family:sans-serif;padding:40px">403 — Accès réservé aux superadmins.</h1>'
            )
        return view_func(request, *args, **kwargs)
    return wrapper


_MOIS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
         'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']


def _months_seq(n, now=None):
    if now is None:
        now = timezone.now()
    y, m = now.year, now.month
    seq = []
    for _ in range(n):
        seq.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    seq.reverse()
    return seq


# ── Dashboard ───────────────────────────────────────────────────


@superadmin_required
def dashboard(request):
    total_schools     = School.objects.filter(is_active=True).count()
    total_schools_all = School.objects.count()
    total_classes     = SchoolClass.objects.filter(is_active=True).count()
    total_students    = Student.objects.filter(is_active=True).count()

    total_revenus = (
        Payment.objects.filter(is_cancelled=False)
        .aggregate(s=Sum('amount'))['s'] or 0
    )

    ia_agg = Lesson.objects.aggregate(
        cost=Sum('generation_cost_usd'),
        n_ready=Count('id', filter=Q(status='ready')),
        n_errors=Count('id', filter=Q(status='error')),
    )
    total_ia_cost = ia_agg['cost'] or 0
    ia_ready      = ia_agg['n_ready']
    ia_errors     = ia_agg['n_errors']

    directors_count = User.objects.filter(role=UserRole.DIRECTOR, is_active=True).count()
    teachers_count  = User.objects.filter(role=UserRole.TEACHER,  is_active=True).count()

    seq     = _months_seq(12)
    monthly = (
        Payment.objects.filter(is_cancelled=False)
        .annotate(month=TruncMonth('payment_date'))
        .values('month').annotate(s=Sum('amount'))
        .order_by('month')
    )
    month_map    = {(r['month'].year, r['month'].month): int(r['s'] or 0) for r in monthly}
    chart_labels = [f"{_MOIS[m-1]} {str(y)[2:]}" for y, m in seq]
    chart_values = [month_map.get((y, m), 0) for y, m in seq]

    recent_qs = (
        School.objects.all()
        .order_by('-created_at')
        .annotate(
            classes_count=Count('classes', filter=Q(classes__is_active=True), distinct=True),
            students_count=Count('students', filter=Q(students__is_active=True), distinct=True),
        )
        .prefetch_related(
            Prefetch('users', queryset=User.objects.filter(role=UserRole.DIRECTOR), to_attr='directors')
        )[:10]
    )
    pay_map = {
        row['student__school_id']: int(row['s'] or 0)
        for row in Payment.objects.filter(is_cancelled=False)
            .values('student__school_id').annotate(s=Sum('amount'))
    }
    school_rows = [
        {
            'school':         s,
            'classes_count':  s.classes_count,
            'students_count': s.students_count,
            'director':       s.directors[0] if s.directors else None,
            'revenus':        pay_map.get(s.id, 0),
        }
        for s in recent_qs
    ]

    return render(request, 'superadmin/dashboard.html', {
        'total_schools':     total_schools,
        'total_schools_all': total_schools_all,
        'total_classes':     total_classes,
        'total_students':    total_students,
        'total_revenus':     total_revenus,
        'total_ia_cost':     total_ia_cost,
        'ia_ready':          ia_ready,
        'ia_errors':         ia_errors,
        'directors_count':   directors_count,
        'teachers_count':    teachers_count,
        'chart_labels':      chart_labels,
        'chart_values':      chart_values,
        'school_rows':       school_rows,
    })


# ── Écoles ──────────────────────────────────────────────────────


@superadmin_required
def school_list(request):
    schools = (
        School.objects.all()
        .order_by('-is_active', 'name')
        .annotate(
            classes_count=Count('classes', filter=Q(classes__is_active=True), distinct=True),
            students_count=Count('students', filter=Q(students__is_active=True), distinct=True),
        )
        .prefetch_related(
            Prefetch('users', queryset=User.objects.filter(role=UserRole.DIRECTOR), to_attr='directors')
        )
    )
    pay_map = {
        row['student__school_id']: int(row['s'] or 0)
        for row in Payment.objects.filter(is_cancelled=False)
            .values('student__school_id').annotate(s=Sum('amount'))
    }
    lesson_map = {
        row['school_id']: row['n']
        for row in Lesson.objects.values('school_id').annotate(n=Count('id'))
    }
    school_data = [
        {
            'school':         s,
            'classes_count':  s.classes_count,
            'students_count': s.students_count,
            'director':       s.directors[0] if s.directors else None,
            'revenus':        pay_map.get(s.id, 0),
            'lessons':        lesson_map.get(s.id, 0),
        }
        for s in schools
    ]
    return render(request, 'superadmin/school_list.html', {'school_data': school_data})


@superadmin_required
def school_create(request):
    if request.method == 'POST':
        form = SchoolCreateForm(request.POST, request.FILES)
        if form.is_valid():
            school = form.save()
            messages.success(request, f'École « {school.name} » créée.')
            return redirect('superadmin:director-create', school_id=school.id)
    else:
        form = SchoolCreateForm()
    return render(request, 'superadmin/school_create.html', {'form': form})


@superadmin_required
def school_update(request, school_id):
    school = get_object_or_404(School, id=school_id)
    if request.method == 'POST':
        form = SchoolUpdateForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, f'École « {school.name} » mise à jour.')
            return redirect('superadmin:school-list')
    else:
        form = SchoolUpdateForm(instance=school)
    return render(request, 'superadmin/school_update.html', {'form': form, 'school': school})


@superadmin_required
def school_toggle(request, school_id):
    if request.method != 'POST':
        return redirect('superadmin:school-list')
    school = get_object_or_404(School, id=school_id)
    school.is_active = not school.is_active
    school.save(update_fields=['is_active'])
    messages.success(request, f'École « {school.name} » {"activée" if school.is_active else "désactivée"}.')
    return redirect('superadmin:school-list')


@superadmin_required
def accounting_toggle(request, school_id):
    if request.method != 'POST':
        return redirect('superadmin:school-list')
    school = get_object_or_404(School, id=school_id)
    school.accounting_enabled = not school.accounting_enabled
    school.save(update_fields=['accounting_enabled'])
    messages.success(request, f'Comptabilité « {school.name} » {"activée" if school.accounting_enabled else "désactivée"}.')
    return redirect('superadmin:school-list')


@superadmin_required
def director_create(request, school_id):
    school = get_object_or_404(School, id=school_id)
    if request.method == 'POST':
        form = DirectorCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.school   = school
            user.role     = UserRole.DIRECTOR
            user.is_staff = True
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, f'Directeur « {user.full_name} » créé.')
            return redirect('superadmin:school-list')
    else:
        form = DirectorCreateForm()
    return render(request, 'superadmin/director_create.html', {'form': form, 'school': school})


@superadmin_required
def director_update(request, school_id, director_id):
    school   = get_object_or_404(School, id=school_id)
    director = get_object_or_404(User, id=director_id, school=school, role=UserRole.DIRECTOR)
    if request.method == 'POST':
        form = DirectorUpdateForm(request.POST, instance=director)
        if form.is_valid():
            user = form.save(commit=False)
            if form.cleaned_data.get('password'):
                user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, f'Directeur « {director.full_name} » mis à jour.')
            return redirect('superadmin:school-list')
    else:
        form = DirectorUpdateForm(instance=director)
    return render(request, 'superadmin/director_update.html', {
        'form': form, 'school': school, 'director': director,
    })


# ── Utilisateurs ────────────────────────────────────────────────


@superadmin_required
def user_list(request):
    role_filter = request.GET.get('role', '')
    qs = User.objects.exclude(is_superuser=True).select_related('school').order_by('full_name')
    if role_filter:
        qs = qs.filter(role=role_filter)
    return render(request, 'superadmin/user_list.html', {
        'users':        qs,
        'role_filter':  role_filter,
        'role_choices': [
            ('director', 'Directeurs'),
            ('teacher',  'Enseignants'),
            ('staff',    'Staff'),
            ('promoter', 'Promoteurs'),
            ('parent',   'Parents'),
        ],
    })


@superadmin_required
def user_create(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user      = form.save(commit=False)
            user.role = form.cleaned_data['role']
            school    = form.cleaned_data.get('school')
            if school:
                user.school = school
            if user.role == UserRole.DIRECTOR:
                user.is_staff = True
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, f'Utilisateur « {user.full_name} » créé.')
            return redirect('superadmin:user-list')
    else:
        form = UserCreateForm()
    return render(request, 'superadmin/user_create.html', {'form': form})


@superadmin_required
def user_toggle(request, user_id):
    if request.method != 'POST':
        return redirect('superadmin:user-list')
    user = get_object_or_404(User, id=user_id)
    if user.is_superuser:
        messages.error(request, 'Impossible de modifier un superadmin.')
        return redirect('superadmin:user-list')
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(request, f'Utilisateur « {user.full_name} » {"activé" if user.is_active else "désactivé"}.')
    return redirect('superadmin:user-list')


@superadmin_required
def user_reset_pwd(request, user_id):
    if request.method != 'POST':
        return redirect('superadmin:user-list')
    user = get_object_or_404(User, id=user_id)
    if user.is_superuser:
        messages.error(request, "Impossible de réinitialiser le mot de passe d'un superadmin.")
        return redirect('superadmin:user-list')
    new_pwd = secrets.token_urlsafe(6)
    user.set_password(new_pwd)
    user.save()
    messages.success(request, f'Nouveau mot de passe de {user.full_name} : {new_pwd}')
    return redirect('superadmin:user-list')


# ── Groupes ─────────────────────────────────────────────────────


@superadmin_required
def group_list(request):
    groups = (
        SchoolGroup.objects.all()
        .select_related('owner')
        .annotate(
            schools_count=Count('schools', distinct=True),
            students_count=Count(
                'schools__students',
                filter=Q(schools__students__is_active=True),
                distinct=True,
            ),
        )
        .order_by('name')
    )
    return render(request, 'superadmin/group_list.html', {'groups': groups})


@superadmin_required
def group_create(request):
    promoters = User.objects.filter(role=UserRole.PROMOTER, is_active=True).order_by('full_name')
    schools   = School.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        owner_id   = request.POST.get('owner_id', '').strip()
        school_ids = request.POST.getlist('school_ids')
        errors = {}
        if not name:
            errors['name'] = 'Le nom du groupe est requis.'
        if not owner_id:
            errors['owner_id'] = 'Le promoteur est requis.'
        if not errors:
            owner = get_object_or_404(User, id=owner_id, role=UserRole.PROMOTER)
            group = SchoolGroup.objects.create(name=name, owner=owner)
            if school_ids:
                School.objects.filter(id__in=school_ids).update(group=group)
            messages.success(request, f'Groupe « {name} » créé avec {len(school_ids)} école(s).')
            return redirect('superadmin:group-list')
        return render(request, 'superadmin/group_create.html', {
            'promoters': promoters, 'schools': schools,
            'errors': errors, 'post': request.POST,
        })

    return render(request, 'superadmin/group_create.html', {
        'promoters': promoters, 'schools': schools,
    })


# ── IA & Leçons ─────────────────────────────────────────────────


@superadmin_required
def ia_dashboard(request):
    school_filter = request.GET.get('school', '')
    status_filter = request.GET.get('status', '')

    lessons = Lesson.objects.select_related('school', 'teacher').order_by('-created_at')
    if school_filter:
        lessons = lessons.filter(school_id=school_filter)
    if status_filter:
        lessons = lessons.filter(status=status_filter)

    totals = Lesson.objects.aggregate(
        total_cost=Sum('generation_cost_usd'),
        n_ready=Count('id', filter=Q(status='ready')),
        n_errors=Count('id', filter=Q(status='error')),
        n_total=Count('id'),
    )
    ia_schools = School.objects.filter(lessons__isnull=False).distinct().order_by('name')

    return render(request, 'superadmin/ia_dashboard.html', {
        'lessons':       lessons,
        'totals':        totals,
        'ia_schools':    ia_schools,
        'school_filter': school_filter,
        'status_filter': status_filter,
    })
