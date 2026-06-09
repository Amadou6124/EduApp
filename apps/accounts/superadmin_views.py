from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _

from apps.schools.models import School, SchoolClass
from apps.students.models import Student
from .models import User, UserRole
from .superadmin_forms import SchoolCreateForm, DirectorCreateForm


def superadmin_required(view_func):
    @wraps(view_func)
    @login_required(login_url='/login/')
    def wrapper(request, *args, **kwargs):
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
    )
    school_data = []
    for school in schools:
        classes_count = school.classes.filter(is_active=True).count()
        students_count = Student.objects.filter(school=school, is_active=True).count()
        director = User.objects.filter(school=school, role=UserRole.DIRECTOR).first()
        school_data.append({
            'school': school,
            'classes_count': classes_count,
            'students_count': students_count,
            'director': director,
        })

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
