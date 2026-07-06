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
from django.utils.translation import gettext_lazy as _

from apps.core.mixins import get_school
from apps.students.models import Student

from .models import (
    ClassSubject, Note, NoteType, NoteEntryGrant, Period, SchoolYear,
)
from .permissions import can_enter_notes, can_enter_formatif


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
    raw = BulletinCalculator().calculate_subject_average(note_list, cs.max_grade)
    return round2(raw)


def _level(value, max_grade):
    """Niveau colorimétrique d'une note pour l'affichage lecture seule.

    Aligné exactement sur colorClass de la grille éditable : <50 % rouge,
    <60 % ambre, sinon vert. None si pas de note.
    """
    if value is None:
        return None
    try:
        v = float(value)
        m = float(max_grade or 20)
    except (TypeError, ValueError):
        return None
    if m <= 0:
        return None
    if v < m / 2:
        return 'low'
    if v < m * 0.6:
        return 'mid'
    return 'high'


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
    """Colonnes du bulletin : position 1 = Note de classe, position 2 = Composition."""
    fixed = {1: _('Note de classe'), 2: _('Composition')}
    return [{'pos': p, 'name': fixed.get(p, f'Note {p}'), 'editable': False} for p in positions]


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

    # Bulletin : 2 colonnes fixes — note de classe (pos 1) + composition (pos 2).
    positions = [1, 2]

    rows = []
    for student in students:
        snotes    = notes_by_student.get(student.pk, {})
        note_list = [snotes.get(pos) for pos in positions]
        # Cellules ordonnées pour le template (évite l'accès dict par variable).
        # level = couleur pré-calculée pour l'affichage lecture seule.
        cells = []
        for pos in positions:
            n   = snotes.get(pos)
            val = n.value if (n and not n.is_cancelled) else None
            cells.append({'pos': pos, 'note': n, 'level': _level(val, cs.max_grade)})
        # Valeurs JSON pour Alpine.js (avg temps réel)
        notes_js = json.dumps({
            str(pos): str(snotes[pos].value)
            if snotes.get(pos) and not snotes[pos].is_cancelled
            else ''
            for pos in positions
        })
        avg = _compute_student_avg(cs, note_list)
        rows.append({
            'student':   student,
            'cells':     cells,
            'note_list': note_list,
            'avg':       avg,
            'avg_level': _level(avg, cs.max_grade),
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

    years = school.school_years.order_by('-start_date')

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

    # Base des classes (avant filtrage par cycle de la période)
    classes_qs = school.classes.filter(is_active=True)
    if teacher_class_ids is not None:
        classes_qs = classes_qs.filter(pk__in=teacher_class_ids)

    # Périodes : seulement celles des cycles réellement présents dans ces classes
    # (compositions au fondamental, trimestres au secondaire…), + les héritées « sans cycle ».
    visible_cycles = set(classes_qs.values_list('level', flat=True))
    periods = [
        p for p in active_year.periods.order_by('education_level', 'order')
        if p.education_level is None or p.education_level in visible_cycles
    ]

    # Onglet période actif (ouverte en priorité)
    period_id     = request.GET.get('period')
    active_period = next((p for p in periods if str(p.pk) == period_id), None) if period_id else None
    if not active_period:
        active_period = (
            next((p for p in periods if p.is_notes_open), None)
            or (periods[0] if periods else None)
        )

    open_periods_count = sum(1 for p in periods if p.is_notes_open)

    # La grille ne montre que les classes du cycle de la période sélectionnée.
    if active_period and active_period.education_level:
        classes_qs = classes_qs.filter(level=active_period.education_level)

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
        # Bulletin : complet si note de classe (pos 1) ET composition (pos 2) saisies pour tous.
        full = (len(noted_by_cs_pos.get((cs.pk, 1), ())) == student_count
                and len(noted_by_cs_pos.get((cs.pk, 2), ())) == student_count)
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
        full = (len(noted_cs_pos.get((cs.pk, 1), ())) == student_count
                and len(noted_cs_pos.get((cs.pk, 2), ())) == student_count)
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

    if active_cs:
        is_director, has_grant = _grant_status(request, active_cs, period)
    else:
        is_director = request.user.is_superuser or request.role in (UserRole.DIRECTOR, UserRole.STAFF)
        has_grant = False

    # Lecture seule : l'utilisateur a accès à la matière (assigné/délégué/direction)
    # mais ne peut pas saisir (période fermée) → il consulte au lieu d'être bloqué.
    read_only = bool(active_cs) and not can_enter and can_enter_formatif(user, active_cs)

    return render(request, 'notes/notes_class.html', {
        'school':           school,
        'school_class':     school_class,
        'period':           period,
        'class_subjects':   class_subjects,
        'subjects_status':  subjects_status,
        'active_cs':        active_cs,
        'can_enter':        can_enter,
        'reason':           reason,
        'is_director':      is_director,
        'has_grant':        has_grant,
        'read_only':        read_only,
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

def _grant_status(request, cs, period):
    """(is_director, has_grant) — ouverture ciblée active pour cette (matière, période)."""
    is_director = request.user.is_superuser or request.role in (UserRole.DIRECTOR, UserRole.STAFF)
    has_grant = False
    if is_director and not period.is_notes_open:
        g = cs.entry_grants.filter(period=period).first()
        has_grant = bool(g and g.is_active())
    return is_director, has_grant


def _render_subject_tabs(request, school_class, period, cs):
    """Rend le wrapper d'onglets (Bulletin/Formatif) d'une matière."""
    can_enter, reason = can_enter_notes(request.user, cs, period)
    students = list(
        Student.objects
        .filter(school_class=school_class, school=school_class.school, is_active=True)
        .order_by('full_name')
    )
    positions, columns, rows, class_stats = _build_table_data(cs, students, period)
    is_director, has_grant = _grant_status(request, cs, period)
    read_only = not can_enter and can_enter_formatif(request.user, cs)
    return render(request, 'notes/partials/subject_tabs.html', {
        'cs': cs, 'period': period, 'school_class': school_class,
        'positions': positions, 'columns': columns, 'rows': rows,
        'class_stats': class_stats, 'can_enter': can_enter, 'reason': reason,
        'is_director': is_director, 'has_grant': has_grant, 'read_only': read_only,
    })


@login_required
def notes_subject_table(request, class_id, period_id, subject_id):
    """Partial HTMX — onglets de saisie (Bulletin/Formatif) pour une matière."""
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), pk=class_id)
    period       = get_object_or_404(Period, pk=period_id, school_year__school=school)
    cs           = get_object_or_404(
        ClassSubject, pk=subject_id, school_class=school_class, is_active=True,
    )
    return _render_subject_tabs(request, school_class, period, cs)


@login_required
@require_http_methods(['POST'])
def notes_grant_toggle(request, subject_id, period_id):
    """Ouvre/ferme la saisie bulletin pour une (matière, période) précise (directeur)."""
    school = get_school(request)
    if not (request.user.is_superuser or request.role in (UserRole.DIRECTOR, UserRole.STAFF)):
        return HttpResponse(status=403)
    cs     = get_object_or_404(ClassSubject, pk=subject_id, school_class__school=school, is_active=True)
    period = get_object_or_404(Period, pk=period_id, school_year__school=school)
    existing = cs.entry_grants.filter(period=period).first()
    if existing:
        existing.delete()
        msg = 'Saisie refermée pour cette matière.'
    else:
        NoteEntryGrant.objects.create(class_subject=cs, period=period, granted_by=request.user)
        msg = "Saisie ouverte pour l'enseignant."
    resp = _render_subject_tabs(request, cs.school_class, period, cs)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': msg, 'type': 'success'}})
    return resp


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
        resp = render(request, 'notes/partials/note_cell.html', {
            'cs': cs, 'student': student, 'period': period,
            'position': position, 'note': None,
            'can_enter': False, 'error': reason,
        })
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': reason, 'type': 'error'}})
        return resp

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

    # Position 1 = note de classe (DEVOIR), position 2 = composition.
    note_type = NoteType.DEVOIR if position == 1 else NoteType.COMPOSITION

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


