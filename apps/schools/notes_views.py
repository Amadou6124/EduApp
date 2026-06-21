"""
Module de saisie et suivi des notes — Étape 2/3 bulletins.

URL prefix  : /notes/
Namespace   : notes
Fichier URL : apps/schools/notes_urls.py
"""
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch

from apps.accounts.models import UserRole
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.core.mixins import get_school
from apps.students.models import Student

from .models import (
    ClassSubject, Note, NoteSystem, NoteType, Period, SchoolYear,
)
from .permissions import can_enter_notes


# ─────────────────────────────────────────────────────────────
# Helpers privés
# ─────────────────────────────────────────────────────────────

def _get_active_year(school, year_id=None):
    """Retourne l'année active ou la plus récente pour l'école."""
    if year_id:
        return school.school_years.filter(pk=year_id).first()
    return (
        school.school_years.filter(is_active=True).first()
        or school.school_years.order_by('-start_date').first()
    )


def _compute_student_avg(cs, note_list):
    """
    Calcule la moyenne d'un élève pour une ClassSubject.

    note_list : liste ordonnée de Note|None (index = position-1).
    """
    valid = [n for n in note_list if n is not None and not n.is_cancelled]
    if not valid:
        return None

    if cs.note_system == NoteSystem.DEVOIRS_COMPO:
        # position 1 = devoir, position 2 = composition
        devoir = next((n.value for n in valid if n.position == 1), None)
        compo  = next((n.value for n in valid if n.position == 2), None)
        if devoir is not None and compo is not None:
            return round(devoir * cs.coeff_devoirs + compo * cs.coeff_compo, 2)
        return None

    # Moyenne simple : somme / nb notes valides
    return round(sum(n.value for n in valid) / len(valid), 2)


def _compute_class_stats(rows):
    """
    Calcule les stats globales d'une classe à partir des lignes du tableau.

    Retourne : {'avg': Decimal|None, 'best': dict|None, 'worst': dict|None}
    """
    avgs = [(r['student'], r['avg']) for r in rows if r['avg'] is not None]
    if not avgs:
        return {'avg': None, 'best': None, 'worst': None}
    avg_val = round(sum(a for _, a in avgs) / len(avgs), 2)
    best    = max(avgs, key=lambda x: x[1])
    worst   = min(avgs, key=lambda x: x[1])
    return {
        'avg':   avg_val,
        'best':  {'student': best[0],  'value': best[1]},
        'worst': {'student': worst[0], 'value': worst[1]},
    }


def _build_table_data(cs, students, period, force_min_cols=2):
    """
    Construit les données du tableau de saisie pour une ClassSubject.

    force_min_cols : nombre minimal de colonnes (utilisé par "ajouter une colonne").

    Retourne : (positions, rows, class_stats)
      - positions  : liste d'entiers [1, 2, …]
      - rows       : liste de dicts {student, notes:{pos:Note}, avg}
      - class_stats: dict retourné par _compute_class_stats()
    """
    existing = list(
        Note.objects.filter(
            class_subject=cs,
            period=period,
        ).order_by('student_id', 'position')
        .select_related('entered_by', 'modified_by')
    )
    # Indexer : {student_id: {position: Note}}
    notes_by_student = defaultdict(dict)
    for note in existing:
        notes_by_student[note.student_id][note.position] = note

    if cs.note_system == NoteSystem.DEVOIRS_COMPO:
        positions = [1, 2]  # fixe : 1=devoirs, 2=composition
    else:
        all_pos = {
            pos
            for student_notes in notes_by_student.values()
            for pos in student_notes
            if not student_notes[pos].is_cancelled
        }
        max_pos   = max(all_pos) if all_pos else 0
        n_cols    = max(max_pos + 1, force_min_cols)
        positions = list(range(1, n_cols + 1))

    rows = []
    for student in students:
        snotes    = notes_by_student.get(student.pk, {})
        note_list = [snotes.get(pos) for pos in positions]
        # Cellules ordonnées pour le template (évite l'accès dict par variable)
        cells = [{'pos': pos, 'note': snotes.get(pos)} for pos in positions]
        # Valeurs JSON pour Alpine.js (avg temps réel)
        notes_js = json.dumps({
            str(pos): str(snotes[pos].value)
            if snotes.get(pos) and not snotes[pos].is_cancelled
            else ''
            for pos in positions
        })
        rows.append({
            'student':   student,
            'cells':     cells,
            'note_list': note_list,
            'avg':       _compute_student_avg(cs, note_list),
            'notes_js':  notes_js,
        })

    return positions, rows, _compute_class_stats(rows)


# ─────────────────────────────────────────────────────────────
# Vue 1 : Tableau de bord notes
# ─────────────────────────────────────────────────────────────

@login_required
def notes_dashboard(request):
    """
    Centre de contrôle des notes.
    GET /notes/
    Paramètres GET optionnels : year=<id>, period=<id>
    """
    school      = get_school(request)
    active_year = _get_active_year(school, request.GET.get('year'))

    if not active_year:
        return render(request, 'notes/notes_dashboard.html', {
            'no_year':        True,
            'school':         school,
            'active_section': 'notes',
        })

    years   = school.school_years.order_by('-start_date')
    periods = list(active_year.periods.all())

    # Onglet période actif (ouverte en priorité)
    period_id = request.GET.get('period')
    if period_id:
        active_period = next((p for p in periods if str(p.pk) == period_id), None)
    else:
        active_period = (
            next((p for p in periods if p.is_notes_open), None)
            or (periods[0] if periods else None)
        )

    open_periods_count = sum(1 for p in periods if p.is_notes_open)

    # Filtre enseignant : uniquement ses classes (assigné ou délégué)
    teacher_class_ids = None
    if request.role == UserRole.TEACHER:
        assigned_ids  = ClassSubject.objects.filter(
            teacher=request.user, is_active=True,
        ).values_list('school_class_id', flat=True).distinct()
        delegated_ids = school.classes.filter(
            notes_delegates=request.user, is_active=True,
        ).values_list('pk', flat=True)
        teacher_class_ids = set(assigned_ids) | set(delegated_ids)

    # Base queryset des classes
    classes_qs = school.classes.filter(is_active=True)
    if teacher_class_ids is not None:
        classes_qs = classes_qs.filter(pk__in=teacher_class_ids)

    # Toutes les notes de la période active — 1 seule requête
    notes_meta  = {}   # {cs_id: set(student_id)}
    note_values = []
    if active_period:
        notes_filter = dict(
            class_subject__school_class__school=school,
            period=active_period,
            is_cancelled=False,
        )
        if teacher_class_ids is not None:
            notes_filter['class_subject__school_class_id__in'] = teacher_class_ids
        for row in Note.objects.filter(**notes_filter).values(
            'class_subject_id', 'student_id', 'value'
        ):
            notes_meta.setdefault(row['class_subject_id'], set()).add(row['student_id'])
            note_values.append(float(row['value']))

    # Classes + matières + élèves — 3 requêtes prefetch
    classes = list(
        classes_qs
        .prefetch_related(
            Prefetch(
                'class_subjects',
                queryset=ClassSubject.objects.filter(is_active=True)
                         .select_related('subject'),
                to_attr='active_subjects',
            ),
            Prefetch(
                'students',
                queryset=Student.objects.filter(is_active=True, school=school),
                to_attr='active_students',
            ),
        )
        .order_by('level', 'name')
    )

    class_progress        = []
    subjects_without_notes = 0
    complete_classes       = 0

    for sc in classes:
        student_count = len(sc.active_students)
        subject_data  = []
        all_complete  = student_count > 0

        for cs in sc.active_subjects:
            noted = len(notes_meta.get(cs.pk, set()))
            pct   = int(noted / student_count * 100) if student_count else 0
            done  = (pct == 100 and student_count > 0)
            if not done:
                all_complete = False
            if noted == 0 and student_count > 0:
                subjects_without_notes += 1
            subject_data.append({
                'cs':    cs,
                'noted': noted,
                'total': student_count,
                'pct':   pct,
                'done':  done,
            })

        if all_complete and subject_data:
            complete_classes += 1

        class_progress.append({
            'class':         sc,
            'subjects':      subject_data,
            'student_count': student_count,
            'all_complete':  all_complete and bool(subject_data),
        })

    avg_overall = (
        round(sum(note_values) / len(note_values), 2)
        if note_values else None
    )

    return render(request, 'notes/notes_dashboard.html', {
        'school':         school,
        'active_year':    active_year,
        'years':          years,
        'periods':        periods,
        'active_period':  active_period,
        'class_progress': class_progress,
        'stats': {
            'open_periods':            open_periods_count,
            'subjects_without_notes':  subjects_without_notes,
            'complete_classes':        complete_classes,
            'avg_overall':             avg_overall,
        },
        'active_section': 'notes',
    })


# ─────────────────────────────────────────────────────────────
# Vue 2 : Page saisie par classe
# ─────────────────────────────────────────────────────────────

@login_required
def notes_class(request, class_id, period_id):
    """
    Page de saisie des notes pour une classe et une période.
    GET /notes/<class_id>/<period_id>/
    Paramètre GET optionnel : subject=<class_subject_id>
    """
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), pk=class_id)
    period       = get_object_or_404(Period, pk=period_id, school_year__school=school)
    user         = request.user

    # Sécurité enseignant : accès refusé si la classe ne lui appartient pas
    if user.role == UserRole.TEACHER:
        has_access = (
            ClassSubject.objects.filter(
                school_class=school_class, teacher=user, is_active=True,
            ).exists()
            or school_class.notes_delegates.filter(pk=user.pk).exists()
        )
        if not has_access:
            return HttpResponse(status=403)

    # Matières de la classe selon le rôle
    qs_cs = (
        ClassSubject.objects
        .filter(school_class=school_class, is_active=True)
        .select_related('subject', 'teacher')
        .order_by('order', 'subject__name')
    )

    if user.role == UserRole.TEACHER:
        # Enseignant : ses matières OU classes où il est délégué
        delegated = school_class.notes_delegates.filter(pk=user.pk).exists()
        if not delegated:
            qs_cs = qs_cs.filter(teacher=user)

    class_subjects = list(qs_cs)

    # Matière active (GET ou première disponible)
    subject_id = request.GET.get('subject')
    active_cs  = None
    if subject_id:
        active_cs = next((cs for cs in class_subjects if str(cs.pk) == subject_id), None)
    if not active_cs:
        active_cs = class_subjects[0] if class_subjects else None

    # Contrôle d'accès pour la matière active
    can_enter, reason = (
        can_enter_notes(user, active_cs, period)
        if active_cs
        else (False, 'Aucune matière disponible pour votre compte.')
    )

    # Données du tableau pour la matière active
    positions, rows, class_stats = [], [], {}
    if active_cs:
        students = list(
            Student.objects
            .filter(school_class=school_class, school=school, is_active=True)
            .order_by('full_name')
        )
        positions, rows, class_stats = _build_table_data(active_cs, students, period)

    # Données pour le mode saisie rapide mobile (Phase 5)
    mobile_position = positions[0] if positions else 1
    mobile_students = []
    mobile_existing = {}
    if rows:
        mobile_students = [
            {
                'id':          r['student'].pk,
                'name':        r['student'].full_name,
                'short':       r['student'].full_name.split()[0] if r['student'].full_name else '—',
                'initials':    r['student'].get_initials(),
                'avatar_bg':   r['student'].get_avatar_colors()[0],
                'avatar_text': r['student'].get_avatar_colors()[1],
            }
            for r in rows
        ]
        for r in rows:
            val = json.loads(r['notes_js']).get(str(mobile_position), '')
            if val:
                mobile_existing[str(r['student'].pk)] = val

    return render(request, 'notes/notes_class.html', {
        'school':           school,
        'school_class':     school_class,
        'period':           period,
        'class_subjects':   class_subjects,
        'active_cs':        active_cs,
        'can_enter':        can_enter,
        'reason':           reason,
        'positions':        positions,
        'rows':             rows,
        'class_stats':      class_stats,
        'mobile_students':  mobile_students,
        'mobile_existing':  mobile_existing,
        'mobile_position':  mobile_position,
        'active_section':   'notes',
    })


# ─────────────────────────────────────────────────────────────
# Vue 3 : Partial HTMX — tableau matière
# ─────────────────────────────────────────────────────────────

@login_required
def notes_subject_table(request, class_id, period_id, subject_id):
    """
    Partial HTMX — tableau de saisie pour une matière.
    GET /notes/<class_id>/<period_id>/<subject_id>/
    Réponse : fragment HTML (notes/partials/notes_table.html)
    """
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), pk=class_id)
    period       = get_object_or_404(Period, pk=period_id, school_year__school=school)
    cs           = get_object_or_404(
        ClassSubject, pk=subject_id, school_class=school_class, is_active=True,
    )

    can_enter, reason = can_enter_notes(request.user, cs, period)

    students = list(
        Student.objects
        .filter(school_class=school_class, school=school, is_active=True)
        .order_by('full_name')
    )
    positions, rows, class_stats = _build_table_data(cs, students, period)

    return render(request, 'notes/partials/notes_table.html', {
        'cs':           cs,
        'period':       period,
        'school_class': school_class,
        'positions':    positions,
        'rows':         rows,
        'class_stats':  class_stats,
        'can_enter':    can_enter,
        'reason':       reason,
    })


# ─────────────────────────────────────────────────────────────
# Vue 4 : Sauvegarde HTMX d'une note (upsert)
# ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def note_save(request):
    """
    HTMX POST — créer ou mettre à jour une note.
    POST /notes/note/save/

    Champs POST : class_subject_id, student_id, period_id, position, value
    Retourne    : fragment note_cell.html avec état updated/error/empty
    """
    school = get_school(request)

    try:
        cs_id      = int(request.POST['class_subject_id'])
        student_id = int(request.POST['student_id'])
        period_id  = int(request.POST['period_id'])
        position   = int(request.POST.get('position', 1))
    except (KeyError, ValueError):
        return HttpResponse(
            '<span class="text-red-500 text-xs">Paramètres manquants.</span>',
            status=400,
        )

    cs      = get_object_or_404(ClassSubject, pk=cs_id, school_class__school=school, is_active=True)
    period  = get_object_or_404(Period, pk=period_id, school_year__school=school)
    student = get_object_or_404(Student, pk=student_id, school=school, is_active=True)

    # Vérification permissions
    can_enter, reason = can_enter_notes(request.user, cs, period)
    if not can_enter:
        return render(request, 'notes/partials/note_cell.html', {
            'cs': cs, 'student': student, 'period': period,
            'position': position, 'note': None,
            'can_enter': False, 'error': reason,
        })

    value_str = request.POST.get('value', '').strip()

    # Valeur vide → supprimer la note si elle existe
    if value_str == '':
        Note.objects.filter(
            class_subject=cs, student=student, period=period, position=position,
        ).delete()
        response = render(request, 'notes/partials/note_cell.html', {
            'cs': cs, 'student': student, 'period': period,
            'position': position, 'note': None, 'can_enter': can_enter,
        })
        response['HX-Trigger'] = json.dumps({
            'note-saved': {
                'studentId': student.pk,
                'position':  position,
                'value':     None,
            }
        })
        return response

    # Valider la valeur numérique (virgule ou point acceptés)
    try:
        value = Decimal(value_str.replace(',', '.'))
    except InvalidOperation:
        response = render(request, 'notes/partials/note_cell.html', {
            'cs': cs, 'student': student, 'period': period,
            'position': position, 'note': None, 'can_enter': can_enter,
            'error': 'Valeur non numérique.',
        })
        response['HX-Trigger'] = json.dumps({
            'note-saved': {
                'studentId': student.pk,
                'position':  position,
                'value':     None,
            }
        })
        return response

    if value < Decimal('0') or value > cs.max_grade:
        response = render(request, 'notes/partials/note_cell.html', {
            'cs': cs, 'student': student, 'period': period,
            'position': position, 'note': None, 'can_enter': can_enter,
            'error': f'Entre 0 et {cs.max_grade}.',
        })
        response['HX-Trigger'] = json.dumps({
            'note-saved': {
                'studentId': student.pk,
                'position':  position,
                'value':     None,
            }
        })
        return response

    # Déduire le type de note selon le système et la position
    if cs.note_system == NoteSystem.DEVOIRS_COMPO:
        note_type = NoteType.DEVOIR if position == 1 else NoteType.COMPOSITION
    else:
        note_type = NoteType.SIMPLE

    # Upsert — unique_together garantit l'unicité (student, class_subject, period, position)
    note, created = Note.objects.get_or_create(
        class_subject=cs,
        student=student,
        period=period,
        position=position,
        defaults={
            'value':        value,
            'note_type':    note_type,
            'entered_by':   request.user,
            'is_cancelled': False,
        },
    )
    if not created:
        note.value        = value
        note.note_type    = note_type
        note.modified_by  = request.user
        note.is_cancelled = False
        note.save(update_fields=['value', 'note_type', 'modified_by', 'modified_at', 'is_cancelled'])

    response = render(request, 'notes/partials/note_cell.html', {
        'cs': cs, 'student': student, 'period': period,
        'position': position, 'note': note,
        'can_enter': can_enter, 'saved': True,
    })
    response['HX-Trigger'] = json.dumps({
        'note-saved': {
            'studentId': student.pk,
            'position':  position,
            'value':     str(note.value),
        }
    })
    return response


# ─────────────────────────────────────────────────────────────
# Vue 5 : Annulation soft (directeur uniquement)
# ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def note_cancel(request, note_id):
    """
    HTMX POST — annulation soft d'une note.
    POST /notes/note/<note_id>/cancel/
    Réservé au directeur et au staff.
    """
    school = get_school(request)
    user   = request.user

    if user.role not in (UserRole.DIRECTOR, UserRole.STAFF) and not user.is_superuser:
        return HttpResponse(
            '<span class="text-red-500 text-xs">Réservé au directeur.</span>',
            status=403,
        )

    note   = get_object_or_404(Note, pk=note_id, class_subject__school_class__school=school)
    reason = request.POST.get('reason', '').strip()

    note.is_cancelled       = True
    note.cancellation_reason = reason
    note.modified_by        = user
    note.save(update_fields=['is_cancelled', 'cancellation_reason', 'modified_by', 'modified_at'])

    resp = render(request, 'notes/partials/note_cell.html', {
        'cs':        note.class_subject,
        'student':   note.student,
        'period':    note.period,
        'position':  note.position,
        'note':      note,
        'can_enter': True,
        'cancelled': True,
    })
    resp['HX-Trigger'] = json.dumps({
        'showToast': {'message': 'Note annulée.', 'type': 'info'}
    })
    return resp


# ─────────────────────────────────────────────────────────────
# Vue 6 : Ajouter une colonne (mode moyenne_simple)
# ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def notes_add_column(request, class_id, period_id, subject_id):
    """
    HTMX POST — ajouter une colonne de note (mode moyenne_simple uniquement).
    POST /notes/<class_id>/<period_id>/<subject_id>/add-column/
    POST body : current_columns=<int>
    Retourne  : fragment notes_table.html avec une colonne de plus.
    """
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), pk=class_id)
    period       = get_object_or_404(Period, pk=period_id, school_year__school=school)
    cs           = get_object_or_404(
        ClassSubject, pk=subject_id, school_class=school_class, is_active=True,
    )

    if cs.note_system != NoteSystem.MOYENNE_SIMPLE:
        return HttpResponse(status=400)

    can_enter, reason = can_enter_notes(request.user, cs, period)
    if not can_enter:
        return HttpResponse(
            f'<span class="text-red-500 text-xs">{reason}</span>',
            status=403,
        )

    current_columns = int(request.POST.get('current_columns', 2))
    students = list(
        Student.objects
        .filter(school_class=school_class, school=school, is_active=True)
        .order_by('full_name')
    )
    # Forcer au moins current_columns + 1 colonnes
    positions, rows, class_stats = _build_table_data(
        cs, students, period, force_min_cols=current_columns + 1,
    )

    return render(request, 'notes/partials/notes_table.html', {
        'cs':           cs,
        'period':       period,
        'school_class': school_class,
        'positions':    positions,
        'rows':         rows,
        'class_stats':  class_stats,
        'can_enter':    can_enter,
        'reason':       reason,
    })
