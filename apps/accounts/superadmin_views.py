from functools import wraps

from django.db.models import Count, Q, Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.utils.translation import gettext_lazy as _

from apps.schools.models import School, SchoolClass
from apps.students.models import Student
from .models import User, UserRole
from .superadmin_forms import SchoolCreateForm, DirectorCreateForm


def superadmin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/admin/login/?next={request.path}')
        if not request.user.is_superuser:
            return HttpResponseForbidden(
                '<h1 style="font-family:sans-serif;padding:40px">403 — Accès réservé aux superadmins.</h1>'
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def _global_stats():
    return {
        'total_schools': School.objects.filter(is_active=True).count(),
        'total_classes': SchoolClass.objects.filter(is_active=True).count(),
        'total_students': Student.objects.filter(is_active=True).count(),
    }


@superadmin_required
def dashboard(request):
    schools = (
        School.objects
        .filter(is_active=True)
        .order_by('-created_at')
        .annotate(
            classes_count=Count('classes', filter=Q(classes__is_active=True), distinct=True),
            students_count=Count('students', filter=Q(students__is_active=True), distinct=True),
        )
        .prefetch_related(
            Prefetch(
                'users',
                queryset=User.objects.filter(role=UserRole.DIRECTOR),
                to_attr='directors',
            )
        )
    )
    school_data = [
        {
            'school': s,
            'classes_count': s.classes_count,
            'students_count': s.students_count,
            'director': s.directors[0] if s.directors else None,
        }
        for s in schools
    ]

    return render(request, 'superadmin/dashboard.html', {
        **_global_stats(),
        'school_data': school_data,
    })


@superadmin_required
def school_create(request):
    if request.method == 'POST':
        form = SchoolCreateForm(request.POST, request.FILES)
        if form.is_valid():
            school = form.save()
            return redirect('superadmin:director-create', school_id=school.id)
    else:
        form = SchoolCreateForm()

    return render(request, 'superadmin/school_create.html', {'form': form})


@superadmin_required
def director_create(request, school_id):
    school = get_object_or_404(School, id=school_id)

    if request.method == 'POST':
        form = DirectorCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.school = school
            user.role = UserRole.DIRECTOR
            user.is_staff = True
            user.set_password(form.cleaned_data['password'])
            user.save()
            return redirect('superadmin:dashboard')
    else:
        form = DirectorCreateForm()

    return render(request, 'superadmin/director_create.html', {
        'form': form,
        'school': school,
    })
