import csv
import io
import json
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Q, Subquery, OuterRef, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.payments.models import Payment, PaymentMethod
from apps.schools.models import SchoolClass
from apps.core.mixins import get_school

from .forms import StudentCreateForm, StudentUpdateForm
from .models import Student


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
    elif filter_type == 'unpaid':
        paid_sq = (
            Payment.objects
            .filter(student=OuterRef('pk'), is_cancelled=False)
            .values('student')
            .annotate(s=Sum('amount'))
            .values('s')
        )
        qs = qs.annotate(
            paid=Coalesce(Subquery(paid_sq), 0, output_field=DecimalField())
        ).filter(paid__lt=F('tuition_fee'))
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
    return render(request, 'students/student_list.html', {
        'students':     students,
        'stats':        stats,
        'form':         StudentCreateForm(school=school),
        'classes':      classes,
        'classes_json': classes_json,
        'school':       school,
        'filter_type':  filter_type,
    })


@login_required
@require_http_methods(['POST'])
def student_create(request):
    school = get_school(request)
    form = StudentCreateForm(request.POST, school=school)

    if form.is_valid():
        student = form.save(commit=False)
        student.school      = school
        student.tuition_fee = student.school_class.annual_fee
        student.save()

        initial_amount = form.cleaned_data.get('initial_payment')
        if initial_amount and initial_amount > 0:
            Payment.objects.create(
                student        = student,
                amount         = initial_amount,
                payment_method = form.cleaned_data.get('payment_method') or 'cash',
                collected_by   = request.user,
            )

        if student.parent_phone_number:
            print(
                f'[SMS LOG] → {student.parent_phone_number} : '
                f'{student.full_name} inscrit(e). Code d\'accès : {student.access_code}'
            )

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
    return render(request, 'students/student_detail.html', {
        'student': student,
        'school':  school,
    })


@login_required
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
def student_search(request):
    school = get_school(request)
    query       = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'all')
    class_id    = request.GET.get('class_id')
    qs          = _students_qs(school, filter_type, class_id)

    if query:
        qs = qs.filter(
            Q(full_name__icontains=query)
            | Q(school_class__name__icontains=query)
            | Q(access_code__icontains=query)
        )

    return render(request, 'students/partials/student_table_body.html', {
        'students': list(qs),
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


@login_required
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

    # bulk_create retourne les instances avec PK sous PostgreSQL + Django 6
    created = Student.objects.bulk_create(students_to_create)

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
