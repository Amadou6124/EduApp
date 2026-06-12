"""
Vues module bulletins — /bulletins/
Étape 3/3 bulletins.
"""
import io
import json
import zipfile

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods

from apps.core.mixins import get_school, director_or_staff_required
from apps.students.models import Student

from .models import (
    Bulletin, BulletinConfig, BulletinLine, ClassSubject,
    Note, Period, SchoolClass, SchoolYear, NoteSystem, AppreciationScale,
)
from .services.bulletin_calculator import BulletinCalculator
from .services.bulletin_pdf import (
    generate_bulletin_pdf, generate_class_pdf, save_bulletin_pdf,
)


calculator = BulletinCalculator()

LEVEL_BADGE = {
    'prescolaire':    ('Préscolaire',       'bg-purple-100 text-purple-700 border-purple-200'),
    'fondamental_1':  ('Fond. 1er Cycle',   'bg-blue-100 text-blue-700 border-blue-200'),
    'fondamental_2':  ('Fond. 2ème Cycle',  'bg-indigo-100 text-indigo-700 border-indigo-200'),
    'secondaire_gen': ('Secondaire Gén.',   'bg-green-100 text-green-700 border-green-200'),
    'secondaire_pro': ('Secondaire Pro',    'bg-teal-100 text-teal-700 border-teal-200'),
    'superieur':      ('Supérieur',         'bg-orange-100 text-orange-700 border-orange-200'),
}


# ─────────────────────────────────────────────────────────────
# Vue 1 : Page principale
# ─────────────────────────────────────────────────────────────

@login_required
def bulletins_main(request):
    """
    Page principale /bulletins/ avec 3 onglets.
    Paramètres GET : year, period, class, tab
    """
    school = get_school(request)

    # Années scolaires
    years = list(school.school_years.order_by('-start_date'))
    active_year = None
    year_id = request.GET.get('year')
    if year_id:
        active_year = next((y for y in years if str(y.pk) == year_id), None)
    if not active_year:
        active_year = (
            school.school_years.filter(is_active=True).first()
            or (years[0] if years else None)
        )

    # Périodes
    periods = []
    active_period = None
    if active_year:
        periods = list(active_year.periods.all())
        period_id = request.GET.get('period')
        if period_id:
            active_period = next((p for p in periods if str(p.pk) == period_id), None)
        if not active_period:
            active_period = periods[0] if periods else None

    # Classes
    classes = list(
        school.classes.filter(is_active=True)
        .order_by('level', 'name')
    )
    active_class = None
    class_id = request.GET.get('class')
    if class_id:
        active_class = next((c for c in classes if str(c.pk) == class_id), None)

    # Onglet actif
    active_tab = request.GET.get('tab', 'health')

    # Données pour l'onglet par défaut
    context = {
        'school':          school,
        'years':           years,
        'active_year':     active_year,
        'periods':         periods,
        'active_period':   active_period,
        'classes':         classes,
        'active_class':    active_class,
        'active_tab':      active_tab,
        'active_section':  'bulletins',
        'can_generate':    request.user.role in ('director', 'staff') or request.user.is_superuser,
    }

    # Stats globales si classe + période sélectionnées
    if active_class and active_period:
        stats = _get_class_stats(active_class, active_period, school)
        context.update(stats)
        context['generated_count'] = len(stats['bulletins'])
        context['total_count'] = stats['student_count']
        context['pending_count'] = stats['student_count'] - len(stats['bulletins'])

    if active_class:
        context['subject_count'] = ClassSubject.objects.filter(
            school_class=active_class, is_active=True,
        ).count()
        context['active_class_badge'] = LEVEL_BADGE.get(
            active_class.level,
            ('', 'bg-gray-100 text-gray-600 border-gray-200'),
        )

    return render(request, 'bulletins/bulletins_main.html', context)


# ─────────────────────────────────────────────────────────────
# Vue 2-4 : Onglets HTMX
# ─────────────────────────────────────────────────────────────

@login_required
def health_tab(request):
    """Onglet Santé éducative — partial HTMX."""
    school = get_school(request)
    active_class, active_period = _get_class_and_period(request, school)
    if not active_class or not active_period:
        return HttpResponse('<p class="text-gray-400 text-sm">Sélectionnez une classe et une période.</p>')

    ctx = _get_class_stats(active_class, active_period, school)
    ctx['active_class'] = active_class
    ctx['active_period'] = active_period
    ctx['can_generate'] = request.user.role in ('director', 'staff') or request.user.is_superuser

    return render(request, 'bulletins/partials/health_tab.html', ctx)


@login_required
def bulletins_tab(request):
    """Onglet Bulletins — partial HTMX."""
    school = get_school(request)
    active_class, active_period = _get_class_and_period(request, school)
    if not active_class or not active_period:
        return HttpResponse('<p class="text-gray-400 text-sm">Sélectionnez une classe et une période.</p>')

    students = list(
        Student.objects
        .filter(school_class=active_class, school=school, is_active=True)
        .order_by('full_name')
    )

    # Bulletins existants
    existing = {
        b.student_id: b
        for b in Bulletin.objects.filter(
            period=active_period,
            school_class=active_class,
            is_cancelled=False,
        ).select_related('student')
    }

    with_notes = _students_with_notes(active_period, active_class)
    rows = []
    for student in students:
        bul = existing.get(student.pk)
        rows.append({
            'student':    student,
            'bulletin':   bul,
            'has_notes':  student.pk in with_notes,
        })

    return render(request, 'bulletins/partials/bulletins_tab.html', {
        'rows':           rows,
        'school_class':   active_class,
        'period':         active_period,
        'can_generate':   request.user.role in ('director', 'staff') or request.user.is_superuser,
        'generated_count': len(existing),
        'total_count':     len(students),
        'pending_count':   len(students) - len(existing),
    })


@login_required
def rankings_tab(request):
    """Onglet Classements — partial HTMX."""
    school = get_school(request)
    active_class, active_period = _get_class_and_period(request, school)
    if not active_class or not active_period:
        return HttpResponse('<p class="text-gray-400 text-sm">Sélectionnez une classe et une période.</p>')

    bulletins = list(
        Bulletin.objects.filter(
            period=active_period,
            school_class=active_class,
            is_cancelled=False,
            general_average__isnull=False,
        )
        .select_related('student')
        .order_by('-general_average')
    )

    return render(request, 'bulletins/partials/rankings_tab.html', {
        'bulletins':      bulletins,
        'school_class':   active_class,
        'period':         active_period,
    })


# ─────────────────────────────────────────────────────────────
# Vue 5-6 : Génération
# ─────────────────────────────────────────────────────────────

@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def generate_class_bulletins(request, class_id, period_id):
    """Génère tous les bulletins d'une classe."""
    school = get_school(request)

    school_class = get_object_or_404(
        school.classes.filter(is_active=True), pk=class_id,
    )
    period = get_object_or_404(
        Period, pk=period_id, school_year__school=school,
    )

    try:
        bulletins = calculator.generate_class_bulletins(
            school_class, period, request.user,
        )
    except Exception as e:
        return HttpResponse(
            f'<p class="text-red-500 text-sm">Erreur : {e}</p>',
            status=500,
        )

    # Re-rendre l'onglet bulletins avec les nouveaux bulletins
    students = list(
        Student.objects
        .filter(school_class=school_class, school=school, is_active=True)
        .order_by('full_name')
    )
    existing = {
        b.student_id: b
        for b in Bulletin.objects.filter(
            period=period,
            school_class=school_class,
            is_cancelled=False,
        ).select_related('student')
    }
    with_notes = _students_with_notes(period, school_class)
    rows = []
    for student in students:
        bul = existing.get(student.pk)
        rows.append({
            'student':    student,
            'bulletin':   bul,
            'has_notes':  student.pk in with_notes,
        })

    response = render(request, 'bulletins/partials/bulletins_tab.html', {
        'rows':           rows,
        'school_class':   school_class,
        'period':         period,
        'can_generate':   True,
        'generated_count': len(existing),
        'total_count':     len(students),
        'pending_count':   len(students) - len(existing),
    })
    response['HX-Trigger'] = json.dumps({
        'bullets-generated': {
            'count':   len(bulletins),
            'classId': class_id,
            'periodId': period_id,
        }
    })
    return response


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def generate_student_bulletin(request, student_id, period_id):
    """Génère le bulletin d'un élève spécifique."""
    school = get_school(request)

    student = get_object_or_404(Student, pk=student_id, school=school, is_active=True)
    period = get_object_or_404(Period, pk=period_id, school_year__school=school)

    try:
        with transaction.atomic():
            bulletin = calculator.generate_bulletin(student, period, request.user)
            ranks = calculator.calculate_ranks(period, student.school_class)
            bulletin.rank = ranks.get(student.pk)
            bulletin.class_size = student.school_class.students.filter(is_active=True).count()
            bulletin.first_average = calculator.get_first_average(period, student.school_class)
            bulletin.save(update_fields=['rank', 'class_size', 'first_average'])
    except Exception as e:
        return HttpResponse(
            f'<span class="text-red-500">Erreur : {e}</span>',
            status=500,
        )

    response = render(request, 'bulletins/partials/bulletin_row.html', {
        'student':  student,
        'bulletin': bulletin,
    })
    response['HX-Trigger'] = json.dumps({
        'bullet-generated': {
            'studentId': student.pk,
        }
    })
    return response


# ─────────────────────────────────────────────────────────────
# Vue 7-9 : Preview / Download
# ─────────────────────────────────────────────────────────────

@login_required
@director_or_staff_required
def bulletin_preview(request, bulletin_id):
    """Preview HTML d'un bulletin (modal)."""
    school = get_school(request)
    bulletin = get_object_or_404(
        Bulletin,
        pk=bulletin_id,
        student__school=school,
        is_cancelled=False,
    )
    lines = list(
        bulletin.lines.all()
        .select_related('class_subject__subject')
        .order_by('class_subject__order', 'class_subject__subject__name')
    )
    config = BulletinConfig.objects.filter(school=school).first()
    if not config:
        config = BulletinConfig.objects.create(school=school)

    return render(request, 'bulletins/bulletin_preview.html', {
        'bulletin': bulletin,
        'lines':    lines,
        'config':   config,
    })


@login_required
@director_or_staff_required
def bulletin_download(request, bulletin_id):
    """Téléchargement PDF d'un bulletin."""
    school = get_school(request)
    bulletin = get_object_or_404(
        Bulletin,
        pk=bulletin_id,
        student__school=school,
        is_cancelled=False,
    )

    pdf_bytes = generate_bulletin_pdf(bulletin)
    filename = (
        f'bulletin_{bulletin.student.full_name.replace(" ", "_")}_'
        f'{bulletin.period.name.replace(" ", "_")}.pdf'
    )

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@director_or_staff_required
def bulletin_view_pdf(request, bulletin_id):
    """Ouvre le PDF dans le navigateur (Content-Disposition: inline)."""
    school = get_school(request)
    bulletin = get_object_or_404(
        Bulletin,
        pk=bulletin_id,
        student__school=school,
        is_cancelled=False,
    )
    pdf_bytes = generate_bulletin_pdf(bulletin)
    filename = (
        f'bulletin_{bulletin.student.full_name.replace(" ", "_")}_'
        f'{bulletin.period.name.replace(" ", "_")}.pdf'
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
@director_or_staff_required
def bulletin_download_all(request, class_id, period_id):
    """Téléchargement ZIP de tous les bulletins d'une classe."""
    school = get_school(request)
    school_class = get_object_or_404(
        school.classes.filter(is_active=True), pk=class_id,
    )
    period = get_object_or_404(
        Period, pk=period_id, school_year__school=school,
    )

    bulletins = list(
        Bulletin.objects.filter(
            period=period,
            school_class=school_class,
            is_cancelled=False,
        ).select_related('student')
    )
    if not bulletins:
        return HttpResponse('Aucun bulletin généré.', status=404)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for bulletin in bulletins:
            pdf_bytes = generate_bulletin_pdf(bulletin)
            filename = (
                f'{bulletin.student.full_name.replace(" ", "_")}_'
                f'{bulletin.period.name.replace(" ", "_")}.pdf'
            )
            zf.writestr(filename, pdf_bytes)

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = (
        f'attachment; filename="bulletins_{school_class.name}_'
        f'{period.name.replace(" ", "_")}.zip"'
    )
    return response


# ─────────────────────────────────────────────────────────────
# Helpers privés
# ─────────────────────────────────────────────────────────────

def _get_class_and_period(request, school):
    """Récupère la classe et la période depuis les paramètres GET."""
    class_id = request.GET.get('class')
    period_id = request.GET.get('period')

    active_class = None
    if class_id:
        active_class = school.classes.filter(pk=class_id, is_active=True).first()

    active_period = None
    if period_id:
        active_period = Period.objects.filter(
            pk=period_id,
            school_year__school=school,
        ).first()

    return active_class, active_period


def _student_has_notes(student, period, school_class):
    """Vérifie si un élève a au moins une note pour chaque matière de la classe."""
    cs_count = ClassSubject.objects.filter(
        school_class=school_class, is_active=True,
    ).count()
    if cs_count == 0:
        return False
    noted_count = Note.objects.filter(
        student=student,
        period=period,
        class_subject__school_class=school_class,
        is_cancelled=False,
    ).values('class_subject').distinct().count()
    return noted_count >= cs_count


def _students_with_notes(period, school_class):
    """
    Retourne un set de student_id ayant une note pour chaque matière active de la classe.
    2 requêtes SQL au lieu de 2×N.
    """
    cs_count = ClassSubject.objects.filter(
        school_class=school_class, is_active=True,
    ).count()
    if cs_count == 0:
        return set()

    rows = (
        Note.objects.filter(
            period=period,
            class_subject__school_class=school_class,
            is_cancelled=False,
        )
        .values('student_id')
        .annotate(distinct_subjects=Count('class_subject', distinct=True))
        .filter(distinct_subjects__gte=cs_count)
    )
    return {row['student_id'] for row in rows}


def _get_class_stats(school_class, period, school):
    """Calcule les stats pour l'onglet santé éducative."""
    students = list(
        Student.objects.filter(
            school_class=school_class, school=school, is_active=True,
        )
    )

    # Bulletins existants
    bulletins = {
        b.student_id: b
        for b in Bulletin.objects.filter(
            period=period,
            school_class=school_class,
            is_cancelled=False,
        )
    }

    # Stats
    averages = [b.general_average for b in bulletins.values() if b.general_average is not None]

    return {
        'student_count': len(students),
        'gen_avg': round(sum(averages) / len(averages), 2) if averages else None,
        'success_rate': (
            round(sum(1 for a in averages if a >= 10) / len(averages) * 100, 1)
            if averages else 0
        ),
        'admitted_count': sum(1 for a in averages if a >= 10),
        'difficulty_count': sum(1 for a in averages if a < 10),
        'bulletins': bulletins,
        'students': students,
        'active_period': period,
        'school_class': school_class,
    }