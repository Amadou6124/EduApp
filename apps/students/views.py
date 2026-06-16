import csv
import io
import json
import logging
from datetime import date, datetime, timedelta

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, F, Q, Subquery, OuterRef, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.payments.models import Payment, PaymentMethod
from apps.schools.models import SchoolClass
from apps.core.mixins import get_school, director_or_staff_required
from apps.core.text import norm_name
from apps.dashboard.views import invalidate_dashboard_cache

from .forms import StudentCreateForm, StudentUpdateForm
from .models import (
    Student, StudentGuardian, ParentRelationship,
    StudentEnrollment, EnrollmentStatus,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────



def _students_qs(school, filter_type='all', class_id=None):
    """Queryset de base annoté — 0 N+1 grâce à select_related + prefetch_related."""
    qs = (
        Student.objects
        .filter(school=school, is_active=True)
        .select_related('school_class')
        .prefetch_related('payments')
        .order_by('full_name')
    )
    if filter_type == 'no_parent':
        qs = qs.filter(parent_phone_number='')
    elif filter_type in ('unpaid', 'partial', 'paid'):
        paid_sq = (
            Payment.objects
            .filter(student=OuterRef('pk'), is_cancelled=False)
            .values('student')
            .annotate(s=Sum('amount'))
            .values('s')
        )
        qs = qs.annotate(
            paid=Coalesce(Subquery(paid_sq), 0, output_field=DecimalField())
        )
        if filter_type == 'unpaid':            # Impayés : rien versé
            qs = qs.filter(paid=0)
        elif filter_type == 'partial':         # Partiels : acompte < total
            qs = qs.filter(paid__gt=0, paid__lt=F('tuition_fee'))
        else:                                  # Soldés : à jour
            qs = qs.filter(paid__gte=F('tuition_fee'))
    elif filter_type == 'class' and class_id:
        qs = qs.filter(school_class_id=class_id)
    return qs


def compute_student_stats(school):
    """4 requêtes fixes pour toutes les stats de la liste."""
    today = timezone.now().date()
    base = Student.objects.filter(school=school, is_active=True)
    paid_sq = (
        Payment.objects
        .filter(student=OuterRef('pk'), is_cancelled=False)
        .values('student')
        .annotate(s=Sum('amount'))
        .values('s')
    )
    unpaid_balance = (
        base
        .annotate(paid=Coalesce(Subquery(paid_sq), 0, output_field=DecimalField()))
        .annotate(balance=F('tuition_fee') - F('paid'))
        .filter(balance__gt=0)
        .aggregate(total=Sum('balance'))['total'] or 0
    )
    return {
        'total':          base.count(),
        'enrolled_today': base.filter(enrolled_at__date=today).count(),
        'without_parent': base.filter(parent_phone_number='').count(),
        'unpaid_balance': int(unpaid_balance),
    }


# ── Vues principales ──────────────────────────────────────────────────────────

@login_required
def student_list(request):
    if request.user.role == 'teacher':
        return redirect('teacher:dashboard')
    school = get_school(request)
    filter_type = request.GET.get('filter', 'all')
    class_id    = request.GET.get('class_id')
    students    = list(_students_qs(school, filter_type, class_id))
    stats       = compute_student_stats(school)
    classes     = SchoolClass.objects.filter(school=school, is_active=True).order_by('level', 'name')
    classes_json = json.dumps([
        {'id': c.id, 'name': c.name, 'annual_fee': int(c.annual_fee), 'level': c.level}
        for c in classes
    ])
    nb_classes = len(classes)  # queryset évalué par classes_json — pas de SQL supplémentaire
    return render(request, 'students/student_list.html', {
        'students':      students,
        'stats':         stats,
        'form':          StudentCreateForm(school=school),
        'classes':       classes,
        'classes_json':  classes_json,
        'school':        school,
        'filter_type':   filter_type,
        'page_subtitle': f"{stats['total']} élève{'s' if stats['total'] != 1 else ''} · {nb_classes} classe{'s' if nb_classes != 1 else ''}",
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def student_create(request):
    school = get_school(request)
    form = StudentCreateForm(request.POST, school=school)

    if form.is_valid():
        student = form.save(commit=False)
        student.school      = school
        student.tuition_fee = student.school_class.annual_fee
        student.save()
        invalidate_dashboard_cache(school)

        initial_amount = form.cleaned_data.get('initial_payment')
        if initial_amount and initial_amount > 0:
            Payment.objects.create(
                student        = student,
                amount         = initial_amount,
                payment_method = form.cleaned_data.get('payment_method') or 'cash',
                collected_by   = request.user,
            )

        if student.parent_phone_number:
            logger.info('[SMS] Notification parent à envoyer — élève : %s', student.full_name)

        if request.htmx:
            students = list(_students_qs(school))
            stats    = compute_student_stats(school)
            response = render(request, 'students/partials/student_list_refresh.html', {
                'students':        students,
                'stats':           stats,
                'success_message': f'{student.full_name} inscrit(e) — Code : {student.access_code}',
            })
            response['HX-Trigger'] = json.dumps({
                'close-panel': True,
                'showToast':   {'message': 'Élève inscrit avec succès.', 'type': 'success'},
            })
            return response

    elif request.htmx:
        return render(request, 'students/partials/student_form_fields.html', {'form': form})

    return redirect('students:list')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def student_create_group(request):
    school = get_school(request)
    class_id   = request.POST.get('class_id')
    names_json = request.POST.get('names_data', '[]')
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school)

    try:
        names = [n.strip() for n in json.loads(names_json) if n.strip()]
    except (json.JSONDecodeError, ValueError):
        names = []

    created_students = [
        Student(
            school       = school,
            school_class = school_class,
            full_name    = name,
            tuition_fee  = school_class.annual_fee,
        )
        for name in names
    ]
    Student.objects.bulk_create(created_students)

    if request.htmx:
        students = list(_students_qs(school))
        stats    = compute_student_stats(school)
        n        = len(created_students)
        response = render(request, 'students/partials/student_list_refresh.html', {
            'students':        students,
            'stats':           stats,
            'success_message': _(f'{n} élève(s) inscrit(s) dans {school_class.name}.'),
        })
        response['HX-Trigger'] = json.dumps({
            'close-panel': True,
            'showToast':   {'message': f'{n} élève(s) inscrit(s) avec succès.', 'type': 'success'},
        })
        return response

    return redirect('students:list')


@login_required
def student_detail(request, student_id):
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class').prefetch_related('payments'),
        id=student_id, school=school,
    )

    observations = None
    if request.role in ('director', 'staff') or request.user.is_superuser:
        from apps.teachers.models import StudentObservation
        observations = list(
            StudentObservation.objects
            .filter(student=student, school=school, is_private=False)
            .select_related('student', 'student__school_class', 'teacher', 'read_by')
            .order_by('-created_at')
        )

    guardians = (
        student.guardians.select_related('guardian')
        .order_by('-is_primary', 'created_at')
    )

    # ── Enrichissement fiche (mono-élève → requêtes directes, pas de N+1) ──
    from apps.teachers.models import Attendance
    from apps.schools.models import Note, Period

    today = timezone.now().date()
    absences_recentes = list(
        Attendance.objects
        .filter(student=student, date__gte=today - timedelta(days=30))
        .select_related('teacher')
        .order_by('-date')
    )

    active_period = (
        Period.objects
        .filter(school_year__school=school, school_year__is_active=True)
        .order_by('-is_notes_open', 'order')
        .first()
    )
    notes_periode = []
    if active_period:
        notes_periode = list(
            Note.objects
            .filter(student=student, period=active_period, is_cancelled=False)
            .select_related('class_subject', 'class_subject__subject')
            .order_by('class_subject__order', 'class_subject__subject__name', 'entered_at')
        )

    notifs_parents = list(
        student.notifications
        .select_related('recipient')
        .order_by('-created_at')[:20]
    )

    return render(request, 'students/student_detail.html', {
        'student':           student,
        'school':            school,
        'observations':      observations,
        'guardians':         guardians,
        'absences_recentes': absences_recentes,
        'notes_periode':     notes_periode,
        'active_period':     active_period,
        'notifs_parents':    notifs_parents,
        'is_director':       request.role == 'director' or request.user.is_superuser,
    })


@login_required
@director_or_staff_required
def observation_mark_read(request, student_id, obs_id):
    from apps.teachers.models import StudentObservation

    school = get_school(request)
    obs = get_object_or_404(
        StudentObservation.objects.select_related(
            'student', 'student__school_class', 'teacher', 'read_by',
        ),
        pk=obs_id,
        student_id=student_id,
        school=school,
        is_private=False,
    )
    if not obs.is_read:
        obs.is_read = True
        obs.read_at = timezone.now()
        obs.read_by = request.user
        obs.save(update_fields=['is_read', 'read_at', 'read_by'])

    # Retourne la card complète re-rendue (swap closest .obs-card)
    return render(request, 'students/partials/obs_card.html', {
        'obs': obs, 'student': obs.student,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def observation_share_parent(request, student_id, obs_id):
    """Toggle le partage d'une observation (non-privée) vers les parents + notifie."""
    from apps.teachers.models import StudentObservation
    from apps.notifications.services import notify_guardians
    from apps.notifications.models import NotificationCategory

    school = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school)
    obs = get_object_or_404(
        StudentObservation,
        id=obs_id,
        student=student,
        is_private=False,
    )

    if obs.is_visible_to_parent:
        # Déjà partagé → retirer
        obs.is_visible_to_parent = False
        obs.save(update_fields=['is_visible_to_parent'])
        msg, notif_type = 'Observation retirée du portail parent.', 'info'
    else:
        # Partager + notifier les parents
        obs.is_visible_to_parent = True
        obs.save(update_fields=['is_visible_to_parent'])
        message = obs.parent_message or obs.content[:100]
        notify_guardians(
            student=student,
            category=NotificationCategory.OBSERVATION,
            title=f"Message de l'école concernant {student.full_name}",
            body=message,
            url='/portal/parent/',
            target=obs,
        )
        msg, notif_type = 'Observation partagée avec les parents.', 'success'

    resp = render(request, 'students/partials/obs_share_button.html', {
        'obs': obs, 'student': student,
    })
    resp['HX-Trigger'] = json.dumps({
        'showToast': {'message': msg, 'type': notif_type},
    })
    return resp


@login_required
@director_or_staff_required
def student_update(request, student_id):
    school = get_school(request)
    student = get_object_or_404(
        Student.objects.select_related('school_class').prefetch_related('payments'),
        id=student_id, school=school,
    )

    if request.method == 'POST':
        form = StudentUpdateForm(request.POST, instance=student, school=school)
        if form.is_valid():
            student = form.save()
            # Re-fetch avec relations pour les méthodes financières
            student = get_object_or_404(
                Student.objects.select_related('school_class').prefetch_related('payments'),
                id=student_id, school=school,
            )
            if request.htmx:
                resp = render(request, 'students/partials/student_profile_view.html', {
                    'student': student,
                    'success': True,
                })
                resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Fiche élève mise à jour.', 'type': 'success'}})
                return resp
            return redirect('students:detail', student_id=student.id)

        # Erreurs de validation
        if request.htmx:
            return render(request, 'students/partials/student_profile_edit.html', {
                'student': student,
                'form':    form,
            })
        return render(request, 'students/student_detail.html', {
            'student': student,
            'form':    form,
            'school':  school,
        })

    # GET
    form = StudentUpdateForm(instance=student, school=school)
    if request.htmx:
        return render(request, 'students/partials/student_profile_edit.html', {
            'student': student,
            'form':    form,
        })
    return redirect('students:detail', student_id=student.id)


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def student_withdraw(request, student_id):
    """Retire un élève des listes actives (transfert / abandon / fin d'année).

    Archive l'inscription (StudentEnrollment) puis Student.is_active=False.
    Les données (notes, paiements, bulletins) sont conservées (FK PROTECT).
    Action réservée au directeur.
    """
    school = get_school(request)
    if request.role != 'director' and not request.user.is_superuser:
        return HttpResponse(status=403)

    student = get_object_or_404(Student, id=student_id, school=school, is_active=True)

    status = request.POST.get('status')
    valid = (
        EnrollmentStatus.TRANSFERRED,
        EnrollmentStatus.GRADUATED,
        EnrollmentStatus.WITHDRAWN,
    )
    if status not in valid:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Motif de retrait invalide.', 'type': 'error'},
        })
        return resp

    from apps.schools.models import SchoolYear
    active_year = SchoolYear.objects.filter(school=school, is_active=True).first()

    with transaction.atomic():
        StudentEnrollment.objects.create(
            student=student,
            school=school,
            school_class=student.school_class,
            school_year=active_year,
            status=status,
            enrolled_at=student.enrolled_at.date() if student.enrolled_at else None,
            ended_at=timezone.now().date(),
        )
        student.is_active = False
        student.save(update_fields=['is_active'])

    invalidate_dashboard_cache(school)

    messages.success(
        request,
        f'{student.full_name} retiré ({EnrollmentStatus(status).label}). '
        'Ses données sont conservées.',
    )
    resp = HttpResponse(status=204)
    resp['HX-Redirect'] = reverse('students:list')
    return resp


@login_required
def student_search(request):
    school = get_school(request)
    query       = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'all')
    class_id    = request.GET.get('class_id')
    qs          = _students_qs(school, filter_type, class_id)

    if query:
        # Recherche insensible casse + accents (normalisation Python, sans
        # extension PostgreSQL). Échelle école → filtrage en mémoire acceptable.
        nq = norm_name(query)
        students = [
            s for s in qs
            if nq in norm_name(s.full_name)
            or nq in norm_name(s.school_class.name if s.school_class else '')
            or nq in norm_name(s.access_code)
        ]
    else:
        students = list(qs)

    return render(request, 'students/partials/student_table_body.html', {
        'students': students,
    })


# ── Import Excel ──────────────────────────────────────────────────────────────

@login_required
def student_import_template(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Élèves'

    NUM_COLS = 6

    # ── Ligne 1 : instructions ────────────────────────────────────────
    ws.append([
        'OBLIGATOIRES : Nom complet, Classe  |  OPTIONNELLES : Téléphone parent, '
        'Téléphone élève, Date de naissance, Lien parenté  |  '
        'Les paiements se gèrent directement dans l\'application.'
    ])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=NUM_COLS)
    instr_cell = ws['A1']
    instr_cell.font      = Font(italic=True, color='555555')
    instr_cell.fill      = PatternFill(start_color='F0F4F8', end_color='F0F4F8', fill_type='solid')
    instr_cell.alignment = Alignment(horizontal='left', wrap_text=True)
    ws.row_dimensions[1].height = 30

    # ── Ligne 2 : en-têtes ───────────────────────────────────────────
    headers = [
        'Nom complet *',
        'Classe *',
        'Téléphone parent',
        'Téléphone élève',
        'Date de naissance (JJ/MM/AAAA)',
        'Lien parenté (père/mère/tuteur)',
    ]
    ws.append(headers)
    header_fill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
    for col_idx, cell in enumerate(ws[2], start=1):
        cell.font      = Font(bold=True, color='FFFFFF')
        cell.fill      = header_fill
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[get_column_letter(col_idx)].width = 28

    # ── Lignes 3-4 : exemples ────────────────────────────────────────
    example_fill = PatternFill(start_color='F7F9FC', end_color='F7F9FC', fill_type='solid')
    for row_data in [
        ['Jean Kouassi',  'CP1',    '0700000002', '0700000001', '15/03/2015', 'père'],
        ['Awa Traoré',    '6ème A', '0600000003', '',           '20/07/2013', 'mère'],
    ]:
        ws.append(row_data)
        for cell in ws[ws.max_row]:
            cell.fill = example_fill

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="modele_eleves.xlsx"'
    wb.save(response)
    return response


def _parse_student_rows(file_obj, filename, school):
    """Parse un fichier Excel/CSV et retourne (rows_valides, erreurs).

    Colonnes attendues (6) :
        Nom complet * | Classe * | Téléphone parent | Téléphone élève
        | Date de naissance | Lien parenté
    """
    rows, errors = [], []

    class_map = {
        c.name.lower(): c
        for c in SchoolClass.objects.filter(school=school, is_active=True)
    }
    existing = set(
        Student.objects
        .filter(school=school, is_active=True)
        .values_list('full_name', 'school_class__name')
    )
    relationship_map = {
        'père': 'father', 'pere': 'father', 'papa': 'father', 'father': 'father',
        'mère': 'mother', 'mere': 'mother', 'mama': 'mother', 'mother': 'mother',
        'tuteur': 'guardian', 'tutrice': 'guardian', 'guardian': 'guardian',
    }

    try:
        if filename.lower().endswith('.csv'):
            content  = file_obj.read().decode('utf-8-sig')
            raw_rows = list(csv.reader(io.StringIO(content)))[1:]   # skip header row
            line_offset = 2
        else:
            wb = openpyxl.load_workbook(file_obj, data_only=True)
            ws = wb.active
            # Détection automatique : cherche la ligne d'en-tête ("nom complet")
            # pour gérer les deux formats (avec ou sans ligne d'instructions)
            data_start = 2
            for i, row in enumerate(ws.iter_rows(min_row=1, max_row=5, values_only=True), start=1):
                first = str(row[0] or '').strip().lower()
                if 'nom' in first and 'complet' in first:
                    data_start = i + 1
                    break
            raw_rows = [
                [str(cell.value).strip() if cell.value is not None else '' for cell in row]
                for row in ws.iter_rows(min_row=data_start)
            ]
            line_offset = data_start
    except Exception as exc:
        errors.append({'line': '—', 'name': '—', 'errors': [f'Impossible de lire le fichier : {exc}']})
        return rows, errors

    for line_num, raw in enumerate(raw_rows, start=line_offset):
        if not any(raw):
            continue
        cols = (raw + [''] * 6)[:6]
        name_raw, class_raw, parent_phone, phone, dob_raw, rel_raw = [
            c.strip() for c in cols
        ]
        row_errors = []

        if not name_raw:
            row_errors.append('Nom manquant')

        school_class = class_map.get(class_raw.lower())
        if not school_class:
            row_errors.append(f'Classe « {class_raw} » introuvable')

        dob = None
        if dob_raw:
            for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    dob = datetime.strptime(dob_raw, fmt).date()
                    break
                except ValueError:
                    pass
            if not dob:
                row_errors.append(f'Date « {dob_raw} » non reconnue (attendu JJ/MM/AAAA)')

        parent_relationship = relationship_map.get(rel_raw.lower(), '') if rel_raw else ''
        is_duplicate = bool(school_class and (name_raw, school_class.name) in existing)

        if row_errors:
            errors.append({'line': line_num, 'name': name_raw or '—', 'errors': row_errors})
        else:
            rows.append({
                'name':                name_raw,
                'class_id':            school_class.id,
                'class_name':          school_class.name,
                'phone':               phone,
                'dob':                 dob.isoformat() if dob else '',
                'parent_phone':        parent_phone,
                'parent_relationship': parent_relationship,
                'annual_fee':          int(school_class.annual_fee),
                'is_duplicate':        is_duplicate,
            })

    return rows, errors


@login_required
@require_http_methods(['POST'])
def student_import_preview(request):
    file_obj = request.FILES.get('import_file')
    if not file_obj:
        return HttpResponse('<p class="text-red-600 text-sm p-3">Aucun fichier sélectionné.</p>')

    school = get_school(request)
    rows, errors = _parse_student_rows(file_obj, file_obj.name, school)

    return render(request, 'students/partials/student_import_preview.html', {
        'rows':        rows,
        'parse_errors': errors,
        'duplicates':  [r['name'] for r in rows if r['is_duplicate']],
        'rows_json':   json.dumps(rows),
    })


def _unique_access_codes(school, count):
    """Génère `count` codes à 6 chiffres uniques dans le lot ET absents en base pour cette école."""
    from .models import generate_student_access_code
    existing = set(
        Student.objects.filter(school=school)
        .values_list('access_code', flat=True)
    )
    codes, seen = [], set()
    attempts = 0
    while len(codes) < count:
        attempts += 1
        if attempts > count * 20:
            raise RuntimeError('Impossible de générer assez de codes uniques.')
        code = generate_student_access_code()
        if code not in existing and code not in seen:
            codes.append(code)
            seen.add(code)
    return codes


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def student_import_confirm(request):
    school = get_school(request)
    try:
        rows = json.loads(request.POST.get('rows_data', '[]'))
    except json.JSONDecodeError:
        return HttpResponse('<p class="text-red-600 text-sm p-3">Données invalides.</p>')

    class_cache = {
        c.id: c
        for c in SchoolClass.objects.filter(school=school, is_active=True)
    }

    students_to_create = []
    skipped = 0

    for row in rows:
        if row.get('is_duplicate'):
            skipped += 1
            continue
        sc = class_cache.get(row['class_id'])
        if not sc:
            skipped += 1
            continue

        s = Student(
            school              = school,
            school_class        = sc,
            full_name           = row['name'],
            phone_number        = row.get('phone', ''),
            parent_phone_number = row.get('parent_phone', ''),
            parent_relationship = row.get('parent_relationship', ''),
            tuition_fee         = sc.annual_fee,
        )
        if row.get('dob'):
            try:
                s.date_of_birth = date.fromisoformat(row['dob'])
            except ValueError:
                pass
        students_to_create.append(s)

    # Assigner des codes uniques (lot + base) avant bulk_create
    try:
        codes = _unique_access_codes(school, len(students_to_create))
    except RuntimeError as e:
        return HttpResponse(
            json.dumps({'showToast': {'message': str(e), 'type': 'error'}}),
            status=422,
            content_type='application/json',
        )
    for student, code in zip(students_to_create, codes):
        student.access_code = code

    try:
        created = Student.objects.bulk_create(students_to_create)
    except IntegrityError:
        # Fallback : save() un par un pour régénérer les codes en conflit
        created = []
        for student in students_to_create:
            while True:
                try:
                    student.pk = None
                    student.access_code = _unique_access_codes(school, 1)[0]
                    student.save()
                    created.append(student)
                    break
                except IntegrityError:
                    continue

    if request.htmx:
        students = list(_students_qs(school))
        stats    = compute_student_stats(school)
        response = render(request, 'students/partials/student_list_refresh.html', {
            'students':        students,
            'stats':           stats,
            'success_message': f'{len(created)} élève(s) importé(s), {skipped} ignoré(s).',
        })
        response['HX-Trigger'] = json.dumps({
            'close-import-modal': True,
            'showToast': {'message': f'{len(created)} élève(s) importé(s).', 'type': 'success'},
        })
        return response

    return redirect('students:list')


# ─────────────────────────────────────────────────────────────
# Phase D2 — Parents / Tuteurs (StudentGuardian)
# ─────────────────────────────────────────────────────────────

def _toast_error(message):
    resp = HttpResponse(status=422)
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': 'error'}})
    return resp


def _render_guardian_section(request, student, *, toast=None, toast_type='success', close_panel=False):
    """Re-rend la section parents/tuteurs avec HX-Trigger (toast + fermeture panel)."""
    guardians = (
        student.guardians.select_related('guardian')
        .order_by('-is_primary', 'created_at')
    )
    resp = render(request, 'students/partials/guardian_section.html', {
        'student': student, 'guardians': guardians,
    })
    triggers = {}
    if toast:
        triggers['showToast'] = {'message': toast, 'type': toast_type}
    if close_panel:
        triggers['close-guardian-panel'] = True
    if triggers:
        resp['HX-Trigger'] = json.dumps(triggers)
    return resp


@login_required
@director_or_staff_required
def guardian_search(request, student_id):
    """GET ?phone= → cherche un compte parent. Partial HTMX (carte ou formulaire création)."""
    from apps.accounts.models import User
    from apps.accounts.team_forms import generate_temp_password

    school  = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school)
    phone   = request.GET.get('phone', '').strip()

    found, already_linked, blocked_role = None, False, None
    if phone:
        candidate = User.objects.filter(phone_number=phone).first()
        if candidate and candidate.role != 'parent':
            blocked_role = candidate.get_role_display()
        elif candidate:
            found = candidate
            already_linked = student.guardians.filter(guardian=candidate).exists()

    return render(request, 'students/partials/guardian_search_result.html', {
        'student': student, 'phone': phone, 'searched': bool(phone),
        'found': found, 'already_linked': already_linked, 'blocked_role': blocked_role,
        'gen_password': generate_temp_password(),
        'relationships': ParentRelationship.choices,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def guardian_add(request, student_id):
    """Lier un parent existant (user_id) OU créer un compte parent (full_name+phone+password) + lier."""
    from apps.accounts.models import User
    from apps.accounts.team_forms import generate_temp_password

    school  = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school)

    relationship = request.POST.get('relationship', '')
    if relationship not in {c[0] for c in ParentRelationship.choices}:
        relationship = ''

    user_id = request.POST.get('user_id', '').strip()

    if user_id:
        parent = get_object_or_404(User, id=user_id, role='parent')
    else:
        full_name = request.POST.get('full_name', '').strip()
        phone     = request.POST.get('phone', '').strip()
        if not full_name or not phone:
            return _toast_error('Nom et téléphone obligatoires.')
        if User.objects.filter(phone_number=phone).exists():
            return _toast_error('Ce numéro est déjà utilisé par un compte.')
        parent = User.objects.create_user(
            phone_number=phone,
            password=request.POST.get('password', '').strip() or generate_temp_password(),
            full_name=full_name, role='parent',
        )

    is_first = not student.guardians.exists()
    link, created = StudentGuardian.objects.get_or_create(
        guardian=parent, student=student,
        defaults={'relationship': relationship, 'is_primary': is_first},
    )
    if not created:
        return _render_guardian_section(
            request, student,
            toast=f'{parent.full_name} est déjà lié à cet élève.', toast_type='info',
            close_panel=True,
        )
    return _render_guardian_section(
        request, student,
        toast=f'{parent.full_name} lié à l\'élève.', close_panel=True,
    )


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def guardian_remove(request, student_id, guardian_id):
    """Retire un lien parent (StudentGuardian.pk). Réassigne le contact principal si besoin."""
    school  = get_school(request)
    student = get_object_or_404(Student, id=student_id, school=school)
    link = get_object_or_404(StudentGuardian, id=guardian_id, student=student)

    name, was_primary = link.guardian.full_name, link.is_primary
    link.delete()
    if was_primary:
        nxt = student.guardians.order_by('created_at').first()
        if nxt:
            nxt.is_primary = True
            nxt.save(update_fields=['is_primary'])

    return _render_guardian_section(request, student, toast=f'{name} retiré.', toast_type='info')


# ─────────────────────────────────────────────────────────────
# Suivi global des élèves (admin) — /students/suivi/
# ─────────────────────────────────────────────────────────────

def _difficulty_flagged(school):
    """(abs_map, bul_map, obs_map, active_period, flagged_ids) — partagé entre la page et l'onglet."""
    from apps.teachers.models import Attendance, StudentObservation
    from apps.schools.models import Bulletin

    today = date.today()
    month_start = today.replace(day=1)

    active_year = school.school_years.filter(is_active=True).first()
    active_period = None
    if active_year:
        active_period = (
            active_year.periods.filter(is_notes_open=True).first()
            or active_year.periods.order_by('-order').first()
        )

    abs_map = dict(
        Attendance.objects.filter(school=school, status='absent', date__gte=month_start)
        .values('student_id').annotate(n=Count('id')).values_list('student_id', 'n')
    )
    bul_map = {}
    if active_period:
        bul_map = dict(
            Bulletin.objects.filter(student__school=school, is_cancelled=False, period=active_period)
            .values_list('student_id', 'general_average')
        )
    obs_map = dict(
        StudentObservation.objects.filter(school=school, is_private=False, is_read=False)
        .values('student_id').annotate(n=Count('id')).values_list('student_id', 'n')
    )
    flagged_ids = (
        {sid for sid, n in abs_map.items() if n >= 3}
        | {sid for sid, avg in bul_map.items() if avg is not None and avg < 10}
        | set(obs_map)
    )
    return abs_map, bul_map, obs_map, active_period, flagged_ids


@login_required
@director_or_staff_required
def student_tracking(request):
    """Page suivi global (3 onglets HTMX). Stats résumé chargées d'emblée."""
    from apps.teachers.models import Attendance, StudentObservation
    from apps.notifications.models import Notification

    school = get_school(request)
    tab = request.GET.get('tab', 'absences')

    classes = school.classes.filter(is_active=True).order_by('level', 'name')

    today = timezone.now().date()
    month_start = today.replace(day=1)
    _, _, _, _, flagged_ids = _difficulty_flagged(school)
    stats = {
        'absences_today': Attendance.objects.filter(
            school=school, status='absent', date=today,
        ).count(),
        'obs_unread': StudentObservation.objects.filter(
            school=school, is_private=False, is_read=False,
        ).count(),
        'difficulty_count': len(flagged_ids),
        'notifs_sent_month': Notification.objects.filter(
            school=school, created_at__date__gte=month_start,
        ).count(),
    }

    return render(request, 'students/tracking.html', {
        'classes': classes,
        'tab': tab,
        'stats': stats,
        'school': school,
    })


@login_required
@director_or_staff_required
def tracking_absences(request):
    from apps.teachers.models import Attendance

    school   = get_school(request)
    class_id = request.GET.get('class')
    periode  = request.GET.get('periode', 'today')
    today    = date.today()

    qs = (
        Attendance.objects
        .filter(school=school, status__in=['absent', 'late'])
        .select_related('student', 'school_class', 'teacher')
        .order_by('-date')
    )
    if class_id:
        qs = qs.filter(school_class_id=class_id)
    if periode == 'today':
        qs = qs.filter(date=today)
    elif periode == 'week':
        qs = qs.filter(date__gte=today - timedelta(days=7))
    elif periode == 'month':
        qs = qs.filter(date__gte=today.replace(day=1))

    page = Paginator(qs, 50).get_page(request.GET.get('page', 1))
    classes = school.classes.filter(is_active=True).order_by('level', 'name')
    return render(request, 'students/partials/tracking_absences.html', {
        'absences': page, 'periode': periode, 'class_id': class_id, 'classes': classes,
    })


@login_required
@director_or_staff_required
def tracking_observations(request):
    from apps.teachers.models import StudentObservation

    school = get_school(request)
    filtre = request.GET.get('filtre', 'all')

    qs = (
        StudentObservation.objects
        .filter(school=school, is_private=False)
        .select_related('student', 'student__school_class', 'teacher', 'read_by')
        .order_by('-created_at')
    )
    if filtre == 'unread':
        qs = qs.filter(is_read=False)
    elif filtre == 'shared':
        qs = qs.filter(is_visible_to_parent=True)

    page = Paginator(qs, 50).get_page(request.GET.get('page', 1))
    return render(request, 'students/partials/tracking_observations.html', {
        'observations': page, 'filtre': filtre,
    })


@login_required
@director_or_staff_required
def tracking_difficulty(request):
    """Élèves signalés : absences>=3/mois OU moy<10 OU observations non lues. 4 requêtes."""
    school = get_school(request)
    abs_map, bul_map, obs_map, active_period, flagged_ids = _difficulty_flagged(school)

    students = (
        Student.objects
        .filter(id__in=flagged_ids, school=school, is_active=True)
        .select_related('school_class')
    )

    results = []
    for s in students:
        abs_count = abs_map.get(s.pk, 0)
        avg = bul_map.get(s.pk)
        obs_count = obs_map.get(s.pk, 0)
        score = (
            2 * (abs_count >= 3)
            + 2 * (avg is not None and avg < 10)
            + 1 * (obs_count > 0)
        )
        results.append({
            'student': s, 'absences': abs_count, 'average': avg,
            'obs_unread': obs_count, 'score': score,
            'level': 'critical' if score >= 4 else ('warning' if score >= 2 else 'watch'),
        })
    results.sort(key=lambda x: -x['score'])

    return render(request, 'students/partials/tracking_difficulty.html', {
        'results': results, 'period': active_period,
    })
