"""
Flux formatif — évaluations HORS bulletin (interro écrite/orale, devoir maison…).
Outil de suivi continu de l'enseignant, entre les compositions. Ne compte JAMAIS
sur le bulletin officiel. Le directeur peut publier une évaluation au parent.

URL prefix : /notes/formatif/  ·  Namespace : notes
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserRole
from apps.core.mixins import get_school
from apps.students.models import Student

from .models import (
    ClassSubject, Period, FormativeEvaluation, FormativeGrade, FormativeEvalType,
)
from .permissions import can_enter_formatif


def _is_director(user):
    return user.is_superuser or user.role in (UserRole.DIRECTOR, UserRole.STAFF)


def _get_cs_period(request, class_id, period_id, subject_id):
    school = get_school(request)
    cs = get_object_or_404(
        ClassSubject,
        school_class_id=class_id, subject_id=subject_id,
        school_class__school=school, is_active=True,
    )
    period = get_object_or_404(Period, pk=period_id, school_year__school=school)
    return school, cs, period


def _formatif_ctx(request, cs, period):
    evals = list(
        FormativeEvaluation.objects
        .filter(class_subject=cs, period=period)
        .prefetch_related('grades')
        .order_by('-date', '-created_at')
    )
    students = list(
        Student.objects.filter(school_class=cs.school_class, is_active=True).order_by('full_name')
    )
    gidx = {(g.evaluation_id, g.student_id): g for ev in evals for g in ev.grades.all()}
    rows = []
    for st in students:
        vals, cells = [], []
        for ev in evals:
            g = gidx.get((ev.id, st.pk))
            cells.append({'eval': ev, 'grade': g})
            if g and not g.is_absent and g.value is not None and ev.max_grade:
                # Ramené sur 20 pour une tendance comparable entre évals de barèmes différents.
                vals.append(g.value / ev.max_grade * 20)
        avg = round(sum(vals) / len(vals), 2) if vals else None
        rows.append({'student': st, 'cells': cells, 'avg': avg})
    return {
        'cs': cs, 'period': period, 'school_class': cs.school_class,
        'evals': evals, 'rows': rows, 'students': students,
        'eval_types': FormativeEvalType.choices,
        'can_enter': can_enter_formatif(request.user, cs),
        'can_publish': _is_director(request.user),
        'today': timezone.now().date(),
    }


def _render_panel(request, cs, period):
    return render(request, 'notes/partials/formatif_panel.html',
                  _formatif_ctx(request, cs, period))


@login_required
def formatif_panel(request, class_id, period_id, subject_id):
    _, cs, period = _get_cs_period(request, class_id, period_id, subject_id)
    return _render_panel(request, cs, period)


@login_required
@require_http_methods(['POST'])
def formatif_eval_create(request, class_id, period_id, subject_id):
    _, cs, period = _get_cs_period(request, class_id, period_id, subject_id)
    if not can_enter_formatif(request.user, cs):
        return HttpResponse(status=403)
    date = request.POST.get('date') or timezone.now().date()
    eval_type = request.POST.get('eval_type') or FormativeEvalType.INTERRO_ECRITE
    title = (request.POST.get('title') or '').strip()[:80]
    try:
        max_grade = Decimal(request.POST.get('max_grade') or '20')
        if max_grade < 1:
            raise ValueError
    except (InvalidOperation, ValueError):
        max_grade = Decimal('20')
    FormativeEvaluation.objects.create(
        class_subject=cs, period=period, date=date, eval_type=eval_type,
        title=title, max_grade=max_grade, created_by=request.user,
    )
    resp = _render_panel(request, cs, period)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Évaluation ajoutée.', 'type': 'success'}})
    return resp


@login_required
@require_http_methods(['POST'])
def formatif_grade_save(request, eval_id):
    school = get_school(request)
    ev = get_object_or_404(
        FormativeEvaluation.objects.select_related('class_subject__school_class'),
        pk=eval_id, class_subject__school_class__school=school,
    )
    if not can_enter_formatif(request.user, ev.class_subject):
        return HttpResponse(status=403)
    student = get_object_or_404(Student, pk=request.POST.get('student_id'), school=school)
    raw = (request.POST.get('value') or '').strip()
    absent = request.POST.get('absent') in ('1', 'true', 'on')

    if absent:
        FormativeGrade.objects.update_or_create(
            evaluation=ev, student=student,
            defaults={'value': None, 'is_absent': True},
        )
        return HttpResponse(status=204)
    if raw == '':
        FormativeGrade.objects.filter(evaluation=ev, student=student).delete()
        return HttpResponse(status=204)
    try:
        val = Decimal(raw)
        if val < 0 or val > ev.max_grade:
            raise ValueError
    except (InvalidOperation, ValueError):
        return HttpResponse(
            f'<span class="text-red-500 text-[10px]">0–{ev.max_grade}</span>',
            status=400,
        )
    FormativeGrade.objects.update_or_create(
        evaluation=ev, student=student,
        defaults={'value': val, 'is_absent': False},
    )
    return HttpResponse(status=204)


@login_required
@require_http_methods(['DELETE'])
def formatif_eval_delete(request, eval_id):
    school = get_school(request)
    ev = get_object_or_404(
        FormativeEvaluation.objects.select_related('class_subject'),
        pk=eval_id, class_subject__school_class__school=school,
    )
    if not can_enter_formatif(request.user, ev.class_subject):
        return HttpResponse(status=403)
    cs, period = ev.class_subject, ev.period
    ev.delete()
    resp = _render_panel(request, cs, period)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Évaluation supprimée.', 'type': 'info'}})
    return resp


@login_required
@require_http_methods(['POST'])
def formatif_publish_toggle(request, eval_id):
    school = get_school(request)
    if not _is_director(request.user):
        return HttpResponse(status=403)
    ev = get_object_or_404(
        FormativeEvaluation.objects.select_related('class_subject'),
        pk=eval_id, class_subject__school_class__school=school,
    )
    ev.is_published_to_parent = not ev.is_published_to_parent
    ev.published_at = timezone.now() if ev.is_published_to_parent else None
    ev.save(update_fields=['is_published_to_parent', 'published_at'])
    resp = _render_panel(request, ev.class_subject, ev.period)
    msg = 'Publiée aux parents.' if ev.is_published_to_parent else 'Retirée des parents.'
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': msg, 'type': 'success'}})
    return resp
