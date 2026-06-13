"""
Portail Professeur — apps/teachers/
Namespace URL : teacher

Phase 1 : stubs URL (sidebar fonctionnelle).
Phases 3-6 : implémentation complète de chaque vue.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def teacher_required(view_func):
    """Décorateur réservé aux enseignants (role='teacher') et superusers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != 'teacher' and not request.user.is_superuser:
            return redirect('notes:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────
# Stubs — implémentés dans les Phases 3-6
# ─────────────────────────────────────────────────────────────

@login_required
@teacher_required
def teacher_dashboard(request):
    # Phase 3 : dashboard personnalisé du professeur
    return redirect('notes:dashboard')


@login_required
@teacher_required
def attendance_list(request):
    # Phase 4 : liste des présences / absences
    return redirect('notes:dashboard')


@login_required
@teacher_required
def attendance_class(request, class_id):
    # Phase 4 : saisie présences pour une classe
    return redirect('notes:dashboard')


@login_required
@teacher_required
def attendance_save(request, class_id):
    # Phase 4 : sauvegarde en masse des présences
    return redirect('notes:dashboard')


@login_required
@teacher_required
def teacher_students(request):
    # Phase 6 : liste des élèves du professeur (lecture seule)
    return redirect('notes:dashboard')


@login_required
@teacher_required
def teacher_student_detail(request, student_id):
    # Phase 6 : fiche élève vue professeur
    return redirect('notes:dashboard')


@login_required
@teacher_required
def observation_create(request, student_id):
    # Phase 6 : créer une observation sur un élève
    return redirect('notes:dashboard')
