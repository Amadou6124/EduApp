import csv
import io
import json

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from .models import SchoolClass, School, EducationLevel
from .forms import SchoolClassForm
from apps.core.mixins import get_school

# Correspondance libellés Excel → valeurs modèle
LEVEL_LABELS = {
    'primaire': EducationLevel.PRIMARY,
    'college': EducationLevel.MIDDLE_SCHOOL,
    'collège': EducationLevel.MIDDLE_SCHOOL,
    'lycee': EducationLevel.HIGH_SCHOOL,
    'lycée': EducationLevel.HIGH_SCHOOL,
    'universite': EducationLevel.UNIVERSITY,
    'université': EducationLevel.UNIVERSITY,
}
LEVEL_DISPLAY = {
    EducationLevel.PRIMARY: 'Primaire',
    EducationLevel.MIDDLE_SCHOOL: 'Collège',
    EducationLevel.HIGH_SCHOOL: 'Lycée',
    EducationLevel.UNIVERSITY: 'Université',
}


def _classes_qs(school):
    return (
        SchoolClass.objects
        .filter(school=school, is_active=True)
        .select_related('school')
        .annotate(student_count=Count('students', filter=Q(students__is_active=True)))
    )


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


@login_required
def class_list(request):
    school = get_school(request)
    classes = list(_classes_qs(school))
    total_students, avg_fill_rate = compute_class_stats(classes)

    form = SchoolClassForm()
    return render(request, 'schools/class_list.html', {
        'classes': classes,
        'form': form,
        'school': school,
        'total_students': total_students,
        'avg_fill_rate': avg_fill_rate,
    })


@login_required
@require_http_methods(['POST'])
def class_create(request):
    school = get_school(request)

    # Réactivation d'une classe soft-deletée
    name = request.POST.get('name', '').strip()
    if name:
        existing = SchoolClass.objects.filter(school=school, name=name, is_active=False).first()
        if existing:
            existing.is_active = True
            existing.annual_fee = request.POST.get('annual_fee', existing.annual_fee)
            existing.level = request.POST.get('level', existing.level)
            existing.max_capacity = request.POST.get('max_capacity', existing.max_capacity)
            existing.save()
            if request.htmx:
                classes = list(_classes_qs(school))
                total_students, avg_fill_rate = compute_class_stats(classes)
                resp = render(request, 'schools/partials/class_list_refresh.html', {
                    'classes': classes,
                    'form': SchoolClassForm(),
                    'success_message': _('Classe réactivée avec succès.'),
                    'total_students': total_students,
                    'avg_fill_rate': avg_fill_rate,
                })
                resp['HX-Trigger'] = json.dumps({'close-add-modal': True, 'showToast': {'message': 'Classe réactivée avec succès.', 'type': 'success'}})
                return resp

    form = SchoolClassForm(request.POST)
    if form.is_valid():
        school_class = form.save(commit=False)
        school_class.school = school
        school_class.save()

        # Réponse HTMX : retourne la nouvelle ligne + réinitialise le formulaire
        if request.htmx:
            classes = list(_classes_qs(school))
            total_students, avg_fill_rate = compute_class_stats(classes)
            resp = render(request, 'schools/partials/class_list_refresh.html', {
                'classes': classes,
                'form': SchoolClassForm(),
                'success_message': _('Classe créée avec succès.'),
                'total_students': total_students,
                'avg_fill_rate': avg_fill_rate,
            })
            resp['HX-Trigger'] = json.dumps({'close-add-modal': True, 'showToast': {'message': 'Classe créée avec succès.', 'type': 'success'}})
            return resp

    if request.htmx:
        return render(request, 'schools/partials/class_form_fields.html', {
            'form': form,
        })

    return render(request, 'schools/class_list.html', {
        'form': form,
        'school': school,
        'classes': list(_classes_qs(school)),
    })


@login_required
def class_edit_form(request, class_id):
    school = get_school(request)
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school)
    form = SchoolClassForm(instance=school_class)
    return render(request, 'schools/partials/class_edit_row.html', {
        'form': form,
        'school_class': school_class,
    })


@login_required
@require_http_methods(['POST'])
def class_update(request, class_id):
    school = get_school(request)
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school)
    form = SchoolClassForm(request.POST, instance=school_class)

    if form.is_valid():
        form.save()
        resp = render(request, 'schools/partials/class_row.html', {
            'school_class': school_class,
            'success': True,
        })
        resp['HX-Trigger'] = json.dumps({
            'close-edit-modal': True,
            'showToast': {'message': f'Classe {school_class.name} modifiée.', 'type': 'success'},
        })
        return resp

    return render(request, 'schools/partials/class_edit_row.html', {
        'form': form,
        'school_class': school_class,
    })


@login_required
def class_search(request):
    school = get_school(request)
    query = request.GET.get('q', '').strip()
    classes = list(
        _classes_qs(school).filter(name__icontains=query)
        if query else
        _classes_qs(school)
    )

    return render(request, 'schools/partials/class_table_body.html', {
        'classes': classes,
    })


@login_required
def class_edit_modal(request, class_id):
    school = get_school(request)
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school)
    form = SchoolClassForm(instance=school_class)
    return render(request, 'schools/partials/class_edit_modal.html', {
        'form': form,
        'school_class': school_class,
    })


@login_required
def class_row(request, class_id):
    school = get_school(request)
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school)
    return render(request, 'schools/partials/class_row.html', {
        'school_class': school_class,
    })


@login_required
def class_import_template(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Classes'

    # En-têtes avec mise en forme
    headers = ['Nom', 'Niveau', 'Frais annuels (FCFA)', 'Capacité max']
    ws.append(headers)
    header_fill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
    for col_idx, cell in enumerate(ws[1], start=1):
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[get_column_letter(col_idx)].width = 22

    # Ligne d'exemple
    ws.append(['CP1', 'Primaire', 120000, 35])
    ws.append(['6ème A', 'Collège', 180000, 40])

    # Note sur les valeurs valides pour Niveau
    ws['F1'] = 'Valeurs valides pour Niveau :'
    ws['F1'].font = Font(italic=True, color='888888')
    for i, label in enumerate(['Primaire', 'Collège', 'Lycée', 'Université'], start=2):
        ws[f'F{i}'] = label
        ws[f'F{i}'].font = Font(italic=True, color='888888')

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="modele_classes.xlsx"'
    wb.save(response)
    return response


def _parse_import_rows(file_obj, filename):
    rows = []
    errors = []

    try:
        if filename.lower().endswith('.csv'):
            content = file_obj.read().decode('utf-8-sig')
            reader = csv.reader(io.StringIO(content))
            next(reader, None)
            raw_rows = list(reader)
        else:
            wb = openpyxl.load_workbook(file_obj, data_only=True)
            ws = wb.active
            raw_rows = [
                [str(cell.value).strip() if cell.value is not None else '' for cell in row]
                for row in ws.iter_rows(min_row=2)
            ]
    except Exception as exc:
        errors.append(f'Impossible de lire le fichier : {exc}')
        return rows, errors

    for line_num, raw in enumerate(raw_rows, start=2):
        if not any(raw):
            continue
        # Colonnes : Nom | Niveau | Frais | Capacité
        cols = (raw + ['', '', '', ''])[:4]
        name, level_raw, fee_raw, capacity_raw = [c.strip() for c in cols]

        row_errors = []

        if not name:
            row_errors.append('Nom manquant')

        level_key = level_raw.lower().replace('\xa0', ' ').strip()
        level = LEVEL_LABELS.get(level_key)
        if not level:
            row_errors.append(f'Niveau "{level_raw}" non reconnu')

        try:
            annual_fee = int(float(fee_raw.replace(' ', '').replace('\xa0', '')))
            if annual_fee < 0:
                raise ValueError
        except (ValueError, AttributeError):
            annual_fee = None
            row_errors.append('Frais annuels invalides')

        try:
            max_capacity = int(float(capacity_raw)) if capacity_raw else None
        except ValueError:
            max_capacity = None
            row_errors.append('Capacité invalide')

        if row_errors:
            errors.append({'line': line_num, 'name': name or '—', 'errors': row_errors})
        else:
            rows.append({
                'name': name,
                'level': level,
                'level_display': LEVEL_DISPLAY[level],
                'annual_fee': annual_fee,
                'max_capacity': max_capacity,
            })

    return rows, errors


@login_required
@require_http_methods(['POST'])
def class_import_preview(request):
    file_obj = request.FILES.get('import_file')
    if not file_obj:
        return HttpResponse('<p class="text-red-600 text-sm">Aucun fichier sélectionné.</p>')

    rows, errors = _parse_import_rows(file_obj, file_obj.name)
    school = get_school(request)

    # Détecter les doublons avec les classes existantes
    existing_names = set(
        SchoolClass.objects.filter(school=school, is_active=True).values_list('name', flat=True)
    )
    duplicates = [r['name'] for r in rows if r['name'] in existing_names]

    return render(request, 'schools/partials/class_import_preview.html', {
        'rows': rows,
        'parse_errors': errors,
        'duplicates': duplicates,
        'rows_json': json.dumps(rows),
    })


@login_required
@require_http_methods(['POST'])
def class_import_confirm(request):
    school = get_school(request)
    rows_json = request.POST.get('rows_data', '[]')

    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError:
        return HttpResponse('<p class="text-red-600 text-sm">Données invalides.</p>')

    created, skipped, reactivated = 0, 0, 0
    for row in rows:
        obj, was_created = SchoolClass.objects.get_or_create(
            school=school,
            name=row['name'],
            defaults={
                'level': row['level'],
                'annual_fee': row['annual_fee'],
                'max_capacity': row.get('max_capacity'),
                'is_active': True,
            },
        )
        if was_created:
            created += 1
        elif not obj.is_active:
            obj.is_active = True
            obj.level = row['level']
            obj.annual_fee = row['annual_fee']
            obj.max_capacity = row.get('max_capacity')
            obj.save()
            reactivated += 1
        else:
            skipped += 1

    msg = f'{created} classe(s) importée(s).'
    if reactivated:
        msg += f' {reactivated} réactivée(s).'
    if skipped:
        msg += f' {skipped} ignorée(s) (doublon).'

    classes = list(SchoolClass.objects.filter(school=school, is_active=True).select_related('school'))
    total_students, avg_fill_rate = compute_class_stats(classes)

    resp = render(request, 'schools/partials/class_list_refresh.html', {
        'classes': classes,
        'success_message': msg,
        'total_students': total_students,
        'avg_fill_rate': avg_fill_rate,
    })
    resp['HX-Trigger'] = json.dumps({'close-import-modal': True, 'showToast': {'message': msg, 'type': 'success'}})
    return resp


@login_required
@require_http_methods(['DELETE'])
def class_delete(request, class_id):
    school = get_school(request)
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school)
    student_count = school_class.get_student_count()
    if student_count > 0:
        response = HttpResponse(status=422)
        response['HX-Trigger'] = json.dumps({
            'showToast': {
                'message': f'Impossible : {student_count} élève(s) inscrit(s) dans cette classe.',
                'type': 'error',
            }
        })
        return response
    name = school_class.name
    school_class.is_active = False
    school_class.save()
    response = HttpResponse('')
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': f'Classe {name} supprimée.', 'type': 'success'}
    })
    return response
