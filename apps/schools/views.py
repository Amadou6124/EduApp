import csv
import io
import json

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from .models import SchoolClass, School, EducationLevel
from .forms import SchoolClassForm

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


@require_http_methods(['POST'])
def class_import_preview(request):
    file_obj = request.FILES.get('import_file')
    if not file_obj:
        return HttpResponse('<p class="text-red-600 text-sm">Aucun fichier sélectionné.</p>')

    rows, errors = _parse_import_rows(file_obj, file_obj.name)
    school = get_demo_school()

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


@require_http_methods(['POST'])
def class_import_confirm(request):
    school = get_demo_school()
    rows_json = request.POST.get('rows_data', '[]')

    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError:
        return HttpResponse('<p class="text-red-600 text-sm">Données invalides.</p>')

    created, skipped = 0, 0
    for row in rows:
        _, was_created = SchoolClass.objects.get_or_create(
            school=school,
            name=row['name'],
            defaults={
                'level': row['level'],
                'annual_fee': row['annual_fee'],
                'max_capacity': row.get('max_capacity'),
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    classes = list(SchoolClass.objects.filter(school=school, is_active=True).select_related('school'))
    total_students, avg_fill_rate = compute_class_stats(classes)

    msg = f'{created} classe(s) importée(s).'
    if skipped:
        msg += f' {skipped} ignorée(s) (doublon).'

    return render(request, 'schools/partials/class_list_refresh.html', {
        'classes': classes,
        'success_message': msg,
        'total_students': total_students,
        'avg_fill_rate': avg_fill_rate,
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
