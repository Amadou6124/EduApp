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
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.core.mixins import get_school
from apps.students.models import Student

from .models import (
    ClassSubject, EvaluationColumn, Note, NoteSystem, NoteType, Period, SchoolYear,
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
    Moyenne d'un élève pour une ClassSubject.

    SOURCE UNIQUE : réutilise exactement la formule du bulletin (BulletinCalculator),
    pour que l'aperçu de saisie ne diverge jamais de la moyenne imprimée sur le bulletin.
    note_list : liste ordonnée de Note|None (index = position-1).
    """
    from apps.schools.services.bulletin_calculator import BulletinCalculator, round2
    raw = BulletinCalculator().calculate_subject_average(
        note_list, cs.note_system, cs.coeff_devoirs, cs.coeff_compo, cs.max_grade,
    )
    return round2(raw)


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


def _column_names(cs, period, positions):
    """Noms des colonnes : fixes en devoir/compo, nommables (EvaluationColumn) en moyenne simple.
    Renvoie [{'pos': p, 'name': str, 'editable': bool}]."""
    if cs.note_system == NoteSystem.DEVOIRS_COMPO:
        fixed = {1: _('Devoir'), 2: _('Composition')}
        return [{'pos': p, 'name': fixed.get(p, f'Note {p}'), 'editable': False} for p in positions]
    named = {
        ec.position: ec.name
        for ec in EvaluationColumn.objects.filter(class_subject=cs, period=period)
    }
    return [{'pos': p, 'name': named.get(p) or f'Éval {p}', 'editable': True} for p in positions]


def _build_table_data(cs, students, period, force_min_cols=2):
    """
    Construit les données du tableau de saisie pour une ClassSubject.

    force_min_cols : nombre minimal de colonnes (utilisé par "ajouter une colonne").

    Retourne : (positions, columns, rows, class_stats)
      - positions  : liste d'entiers [1, 2, …]
      - columns    : liste de dicts {pos, name, editable} (en-têtes nommés)
      - rows       : liste de dicts {student, cells, avg, notes_js}
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
        # Positions = colonnes avec notes ∪ colonnes nommées (EvaluationColumn).
        note_pos = {
            pos
            for student_notes in notes_by_student.values()
            for pos in student_notes
            if not student_notes[pos].is_cancelled
        }
        eval_pos = set(
            EvaluationColumn.objects.filter(class_subject=cs, period=period)
            .values_list('position', flat=True)
        )
        all_pos   = note_pos | eval_pos
        max_pos   = max(all_pos) if all_pos else 0
        n_cols    = max(max_pos, force_min_cols)
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

    columns = _column_names(cs, period, positions)
    return positions, columns, rows, _compute_class_stats(rows)


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

    # Notes de la période : maps (cs, position) → élèves notés + valeurs — 1 requête.
    noted_by_cs_pos = defaultdict(set)   # (cs_id, position) -> {student_id}
    positions_by_cs = defaultdict(set)   # cs_id -> {position}
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
            'class_subject_id', 'position', 'student_id', 'value', 'class_subject__max_grade'
        ):
            noted_by_cs_pos[(row['class_subject_id'], row['position'])].add(row['student_id'])
            positions_by_cs[row['class_subject_id']].add(row['position'])
            mg = float(row['class_subject__max_grade'] or 20)
            if mg:
                note_values.append(float(row['value']) / mg * 20)   # normalisé /20

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

    def _cs_status(cs, student_count):
        """non_started | in_progress | complete.

        « complete » n'est revendiqué que si c'est vérifiable : devoir+compo saisis
        pour tous, ou (moyenne simple) toutes les colonnes existantes remplies pour tous.
        Sinon « in_progress » — le vrai « terminé » reste la fermeture de la période.
        """
        if student_count == 0:
            return 'in_progress'
        if cs.pk not in positions_by_cs:
            return 'non_started'
        if cs.note_system == NoteSystem.DEVOIRS_COMPO:
            full = (len(noted_by_cs_pos.get((cs.pk, 1), ())) == student_count
                    and len(noted_by_cs_pos.get((cs.pk, 2), ())) == student_count)
        else:
            full = all(
                len(noted_by_cs_pos.get((cs.pk, p), ())) == student_count
                for p in positions_by_cs[cs.pk]
            )
        return 'complete' if full else 'in_progress'

    class_progress = []
    n_non_started  = n_in_progress = n_complete = 0

    for sc in classes:
        student_count = len(sc.active_students)
        subject_data  = []
        c_started = c_complete = c_non_started = 0
        for cs in sc.active_subjects:
            status = _cs_status(cs, student_count)
            subject_data.append({'cs': cs, 'status': status})
            if student_count == 0:
                continue
            if status == 'non_started':
                n_non_started += 1
                c_non_started += 1
            elif status == 'complete':
                n_complete += 1
                c_complete += 1
                c_started += 1
            else:
                n_in_progress += 1
                c_started += 1
        total_subjects = len(subject_data)
        class_progress.append({
            'class':          sc,
            'subjects':       subject_data,
            'student_count':  student_count,
            'total_subjects': total_subjects,
            'started':        c_started,
            'complete':       c_complete,
            'non_started':    c_non_started,
            'all_complete':   total_subjects > 0 and c_complete == total_subjects,
        })

    avg_overall = (
        round(sum(note_values) / len(note_values), 2)
        if note_values else None
    )

    can_manage = (
        request.user.is_superuser
        or request.role in (UserRole.DIRECTOR, UserRole.STAFF)
    )
    ctx = {
        'school':         school,
        'active_year':    active_year,
        'years':          years,
        'periods':        periods,
        'active_period':  active_period,
        'class_progress': class_progress,
        'can_manage':     can_manage,
        'stats': {
            'open_periods':  open_periods_count,
            'non_started':   n_non_started,
            'in_progress':   n_in_progress,
            'complete':      n_complete,
            'avg_overall':   avg_overall,
        },
        'active_section': 'notes',
    }
    # Onglets périodes en HTMX → on ne renvoie que le corps (swap instantané).
    template = (
        'notes/partials/dashboard_body.html'
        if request.htmx and periods else 'notes/notes_dashboard.html'
    )
    return render(request, template, ctx)


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

    students = list(
        Student.objects
        .filter(school_class=school_class, school=school, is_active=True)
        .order_by('full_name')
    )
    student_count = len(students)

    # Statut par matière (pour le menu déroulant) — 1 requête sur toutes les matières.
    cs_ids = [cs.pk for cs in class_subjects]
    noted_cs_pos = defaultdict(set)   # (cs_id, pos) -> {student_id}
    cs_positions = defaultdict(set)   # cs_id -> {pos}
    for row in Note.objects.filter(
        class_subject_id__in=cs_ids, period=period, is_cancelled=False,
    ).values('class_subject_id', 'position', 'student_id'):
        noted_cs_pos[(row['class_subject_id'], row['position'])].add(row['student_id'])
        cs_positions[row['class_subject_id']].add(row['position'])

    def _status(cs):
        if student_count == 0:
            return 'in_progress'
        if cs.pk not in cs_positions:
            return 'non_started'
        if cs.note_system == NoteSystem.DEVOIRS_COMPO:
            full = (len(noted_cs_pos.get((cs.pk, 1), ())) == student_count
                    and len(noted_cs_pos.get((cs.pk, 2), ())) == student_count)
        else:
            full = all(len(noted_cs_pos.get((cs.pk, p), ())) == student_count
                       for p in cs_positions[cs.pk])
        return 'complete' if full else 'in_progress'

    subjects_status = [{'cs': cs, 'status': _status(cs)} for cs in class_subjects]

    # Données du tableau pour la matière active
    positions, columns, rows, class_stats = [], [], [], {}
    if active_cs:
        positions, columns, rows, class_stats = _build_table_data(active_cs, students, period)

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
        'subjects_status':  subjects_status,
        'active_cs':        active_cs,
        'can_enter':        can_enter,
        'reason':           reason,
        'positions':        positions,
        'columns':          columns,
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
    positions, columns, rows, class_stats = _build_table_data(cs, students, period)

    return render(request, 'notes/partials/notes_table.html', {
        'cs':           cs,
        'period':       period,
        'school_class': school_class,
        'positions':    positions,
        'columns':      columns,
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
    new_pos = current_columns + 1
    # Nom par défaut « Éval N » pour la nouvelle colonne (renommable ensuite).
    EvaluationColumn.objects.get_or_create(
        class_subject=cs, period=period, position=new_pos,
        defaults={'name': f'Éval {new_pos}'},
    )
    students = list(
        Student.objects
        .filter(school_class=school_class, school=school, is_active=True)
        .order_by('full_name')
    )
    # Forcer au moins current_columns + 1 colonnes
    positions, columns, rows, class_stats = _build_table_data(
        cs, students, period, force_min_cols=new_pos,
    )

    return render(request, 'notes/partials/notes_table.html', {
        'cs':           cs,
        'period':       period,
        'school_class': school_class,
        'positions':    positions,
        'columns':      columns,
        'rows':         rows,
        'class_stats':  class_stats,
        'can_enter':    can_enter,
        'reason':       reason,
    })


# ─────────────────────────────────────────────────────────────
# Vue 7 : Ouvrir/fermer la saisie d'une période (directeur/staff)
# ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def notes_period_toggle(request, period_id):
    """
    Ouvre ou ferme la saisie des notes pour une période, puis recharge le dashboard.
    POST /notes/period/<period_id>/toggle/  — réservé directeur / staff.
    """
    school = get_school(request)
    if not (request.user.is_superuser or request.role in (UserRole.DIRECTOR, UserRole.STAFF)):
        return HttpResponse(status=403)

    period = get_object_or_404(Period, pk=period_id, school_year__school=school)
    period.is_notes_open = not period.is_notes_open
    period.save(update_fields=['is_notes_open'])

    return redirect(f"{reverse('notes:dashboard')}?period={period.pk}")


# ─────────────────────────────────────────────────────────────
# Vues 9-10 : Renommer une évaluation · Remplir une colonne
# ─────────────────────────────────────────────────────────────

def _render_table(request, school_class, cs, period, force_min_cols=2):
    """Rend le partial notes_table pour une matière (DRY pour rename / fill)."""
    can_enter, reason = can_enter_notes(request.user, cs, period)
    students = list(
        Student.objects.filter(school_class=school_class, is_active=True).order_by('full_name')
    )
    positions, columns, rows, class_stats = _build_table_data(
        cs, students, period, force_min_cols=force_min_cols,
    )
    return render(request, 'notes/partials/notes_table.html', {
        'cs': cs, 'period': period, 'school_class': school_class,
        'positions': positions, 'columns': columns, 'rows': rows,
        'class_stats': class_stats, 'can_enter': can_enter, 'reason': reason,
    })


@login_required
@require_http_methods(['POST'])
def notes_rename_column(request, class_id, period_id, subject_id, position):
    """Renomme une évaluation (moyenne simple). POST body : name."""
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), pk=class_id)
    period       = get_object_or_404(Period, pk=period_id, school_year__school=school)
    cs           = get_object_or_404(ClassSubject, pk=subject_id, school_class=school_class, is_active=True)

    if cs.note_system != NoteSystem.MOYENNE_SIMPLE:
        return HttpResponse(status=400)
    can_enter, reason = can_enter_notes(request.user, cs, period)
    if not can_enter:
        return HttpResponse(f'<span class="text-red-500 text-xs">{reason}</span>', status=403)

    name = request.POST.get('name', '').strip()[:40] or f'Éval {position}'
    EvaluationColumn.objects.update_or_create(
        class_subject=cs, period=period, position=position, defaults={'name': name},
    )
    return _render_table(request, school_class, cs, period)


@login_required
@require_http_methods(['POST'])
def notes_fill_column(request, class_id, period_id, subject_id, position):
    """Remplit une colonne : même note à tous les élèves SANS note (cellules vides only)."""
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), pk=class_id)
    period       = get_object_or_404(Period, pk=period_id, school_year__school=school)
    cs           = get_object_or_404(ClassSubject, pk=subject_id, school_class=school_class, is_active=True)

    can_enter, reason = can_enter_notes(request.user, cs, period)
    if not can_enter:
        return HttpResponse(f'<span class="text-red-500 text-xs">{reason}</span>', status=403)

    try:
        value = Decimal(request.POST.get('value', '').strip().replace(',', '.'))
    except InvalidOperation:
        return HttpResponse('<span class="text-red-500 text-xs">Valeur invalide.</span>', status=400)
    if value < Decimal('0') or value > cs.max_grade:
        return HttpResponse(f'<span class="text-red-500 text-xs">Entre 0 et {cs.max_grade}.</span>', status=400)

    if cs.note_system == NoteSystem.DEVOIRS_COMPO:
        note_type = NoteType.DEVOIR if position == 1 else NoteType.COMPOSITION
    else:
        note_type = NoteType.SIMPLE

    students = list(
        Student.objects.filter(school_class=school_class, is_active=True).order_by('full_name')
    )
    # Garde-fou : ne remplir que les cellules vides (aucune ligne existante à cette position).
    occupied = set(
        Note.objects.filter(class_subject=cs, period=period, position=position)
        .values_list('student_id', flat=True)
    )
    Note.objects.bulk_create([
        Note(class_subject=cs, student=s, period=period, position=position,
             value=value, note_type=note_type, entered_by=request.user)
        for s in students if s.pk not in occupied
    ])
    filled = sum(1 for s in students if s.pk not in occupied)

    resp = _render_table(request, school_class, cs, period)
    resp['HX-Trigger'] = json.dumps({'showToast': {
        'message': f'{filled} note{"s" if filled != 1 else ""} remplie{"s" if filled != 1 else ""}.',
        'type': 'success',
    }})
    return resp
