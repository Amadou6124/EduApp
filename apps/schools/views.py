from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from .models import SchoolClass, School
from .forms import SchoolClassForm

# École de démonstration (sera remplacée par le multi-tenant)
DEMO_SCHOOL_ID = 1


def get_demo_school():
    return School.objects.filter(id=DEMO_SCHOOL_ID).first()


def compute_class_stats(classes):
    total_students = sum(c.get_student_count() for c in classes)
    classes_with_capacity = [c for c in classes if c.max_capacity]
    avg_fill_rate = 0
    if classes_with_capacity:
        avg_fill_rate = round(
            sum(min(c.get_student_count() / c.max_capacity * 100, 100) for c in classes_with_capacity)
            / len(classes_with_capacity)
        )
    return total_students, avg_fill_rate


def class_list(request):
    school = get_demo_school()
    classes = list(SchoolClass.objects.filter(school=school, is_active=True).select_related('school'))
    total_students, avg_fill_rate = compute_class_stats(classes)

    form = SchoolClassForm()
    return render(request, 'schools/class_list.html', {
        'classes': classes,
        'form': form,
        'school': school,
        'total_students': total_students,
        'avg_fill_rate': avg_fill_rate,
    })


@require_http_methods(['POST'])
def class_create(request):
    school = get_demo_school()
    form = SchoolClassForm(request.POST)

    if form.is_valid():
        school_class = form.save(commit=False)
        school_class.school = school
        school_class.save()

        # Réponse HTMX : retourne la nouvelle ligne + réinitialise le formulaire
        if request.htmx:
            classes = list(SchoolClass.objects.filter(school=school, is_active=True).select_related('school'))
            total_students, avg_fill_rate = compute_class_stats(classes)
            return render(request, 'schools/partials/class_list_refresh.html', {
                'classes': classes,
                'form': SchoolClassForm(),
                'success_message': _('Classe créée avec succès.'),
                'total_students': total_students,
                'avg_fill_rate': avg_fill_rate,
            })

    if request.htmx:
        return render(request, 'schools/partials/class_form_fields.html', {
            'form': form,
        })

    return render(request, 'schools/class_list.html', {
        'form': form,
        'school': school,
        'classes': SchoolClass.objects.filter(school=school, is_active=True),
    })


def class_edit_form(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)
    form = SchoolClassForm(instance=school_class)
    return render(request, 'schools/partials/class_edit_row.html', {
        'form': form,
        'school_class': school_class,
    })


@require_http_methods(['POST'])
def class_update(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)
    form = SchoolClassForm(request.POST, instance=school_class)

    if form.is_valid():
        form.save()
        return render(request, 'schools/partials/class_row.html', {
            'school_class': school_class,
            'success': True,
        })

    return render(request, 'schools/partials/class_edit_row.html', {
        'form': form,
        'school_class': school_class,
    })


def class_search(request):
    school = get_demo_school()
    query = request.GET.get('q', '').strip()

    classes = list(
        SchoolClass.objects.filter(
            school=school,
            is_active=True,
            name__icontains=query,
        ).select_related('school')
        if query else
        SchoolClass.objects.filter(school=school, is_active=True).select_related('school')
    )

    return render(request, 'schools/partials/class_table_body.html', {
        'classes': classes,
    })


def class_edit_modal(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)
    form = SchoolClassForm(instance=school_class)
    return render(request, 'schools/partials/class_edit_modal.html', {
        'form': form,
        'school_class': school_class,
    })


def class_row(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)
    return render(request, 'schools/partials/class_row.html', {
        'school_class': school_class,
    })


@require_http_methods(['DELETE'])
def class_delete(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)
    # Désactivation douce : on ne supprime pas si des élèves sont inscrits
    if school_class.get_student_count() > 0:
        return HttpResponse(
            f'<div class="text-red-600 text-sm p-2">{_("Impossible : des élèves sont inscrits dans cette classe.")}</div>',
            status=422,
        )
    school_class.is_active = False
    school_class.save()
    return HttpResponse('')
