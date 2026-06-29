import csv
import io
import json

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from django.contrib.auth.decorators import login_required
from django.urls import reverse

from apps.accounts.models import UserRole
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from .models import SchoolClass, School, EducationLevel, SchoolAnnouncement
from .forms import SchoolClassForm
from .cockpit import build_class_cockpit
from apps.core.mixins import get_school, director_or_staff_required
from apps.core.text import norm_name

# Correspondance libellés Excel → valeurs modèle
LEVEL_LABELS = {
    'prescolaire':                EducationLevel.PRESCOLAIRE,
    'préscolaire':                EducationLevel.PRESCOLAIRE,
    'fondamental1':               EducationLevel.FONDAMENTAL_1,
    'fondamental_1':              EducationLevel.FONDAMENTAL_1,
    'fondamental 1er cycle':      EducationLevel.FONDAMENTAL_1,
    'primaire':                   EducationLevel.FONDAMENTAL_1,
    'fondamental2':               EducationLevel.FONDAMENTAL_2,
    'fondamental_2':              EducationLevel.FONDAMENTAL_2,
    'fondamental 2ème cycle':     EducationLevel.FONDAMENTAL_2,
    'fondamental 2eme cycle':     EducationLevel.FONDAMENTAL_2,
    'college':                    EducationLevel.FONDAMENTAL_2,
    'collège':                    EducationLevel.FONDAMENTAL_2,
    'secondaire':                 EducationLevel.SECONDAIRE_GEN,
    'secondaire_gen':             EducationLevel.SECONDAIRE_GEN,
    'secondaire général':         EducationLevel.SECONDAIRE_GEN,
    'secondaire general':         EducationLevel.SECONDAIRE_GEN,
    'lycee':                      EducationLevel.SECONDAIRE_GEN,
    'lycée':                      EducationLevel.SECONDAIRE_GEN,
    'secondaire_pro':             EducationLevel.SECONDAIRE_PRO,
    'secondaire professionnel':   EducationLevel.SECONDAIRE_PRO,
    'cap':                        EducationLevel.SECONDAIRE_PRO,
    'universite':                 EducationLevel.SUPERIEUR,
    'université':                 EducationLevel.SUPERIEUR,
    'superieur':                  EducationLevel.SUPERIEUR,
    'supérieur':                  EducationLevel.SUPERIEUR,
    'enseignement supérieur':     EducationLevel.SUPERIEUR,
    'enseignement superieur':     EducationLevel.SUPERIEUR,
}
LEVEL_DISPLAY = {
    EducationLevel.PRESCOLAIRE:    'Préscolaire',
    EducationLevel.FONDAMENTAL_1:  'Fondamental 1er Cycle',
    EducationLevel.FONDAMENTAL_2:  'Fondamental 2ème Cycle',
    EducationLevel.SECONDAIRE_GEN: 'Secondaire Général',
    EducationLevel.SECONDAIRE_PRO: 'Secondaire Professionnel',
    EducationLevel.SUPERIEUR:      'Enseignement Supérieur',
}


def _classes_qs(school):
    return (
        SchoolClass.objects
        .filter(school=school, is_active=True)
        .select_related('school')
        .annotate(
            student_count=Count('students', filter=Q(students__is_active=True)),
            boys=Count('students',  filter=Q(students__is_active=True, students__gender='M')),
            girls=Count('students', filter=Q(students__is_active=True, students__gender='F')),
        )
    )


def compute_class_stats(classes):
    """Agrégats liste classes : effectif, parité, et métrique de capacité honnête
    (places restantes + classes complètes — pas une moyenne plafonnée trompeuse)."""
    with_cap = [c for c in classes if c.max_capacity]
    return {
        'total_classes':     len(classes),
        'total_students':    sum(c.student_count for c in classes),
        'boys':              sum(c.boys for c in classes),
        'girls':             sum(c.girls for c in classes),
        'places_restantes':  sum(max(c.max_capacity - c.student_count, 0) for c in with_cap),
        'classes_completes': sum(1 for c in with_cap if c.student_count >= c.max_capacity),
    }


def _filter_classes(request, school):
    """Classes filtrées : recherche (nom) × niveau × disponibilité (places libres)."""
    qs = _classes_qs(school)
    q     = request.GET.get('q', '').strip()
    level = request.GET.get('level', '')
    if q:
        qs = qs.filter(name__icontains=q)
    if level:
        qs = qs.filter(level=level)
    classes = sorted(qs, key=lambda c: (c.level, c.name))
    if request.GET.get('dispo') in ('1', 'true', 'on'):
        classes = [c for c in classes if not c.is_full]
    return classes


@login_required
def class_list(request):
    if request.user.role == UserRole.TEACHER:
        return redirect('teacher:dashboard')
    school = get_school(request)
    all_classes = list(_classes_qs(school))
    return render(request, 'schools/class_list.html', {
        'classes':        _filter_classes(request, school),
        'form':           SchoolClassForm(),
        'school':         school,
        'cstats':         compute_class_stats(all_classes),
        'levels':         EducationLevel.choices,
        'q':              request.GET.get('q', ''),
        'level':          request.GET.get('level', ''),
        'dispo':          request.GET.get('dispo', ''),
    })


@login_required
def class_detail(request, class_id):
    """Cockpit de classe : KPIs, élèves à risque, moyenne par matière, roster, matières/profs."""
    if request.user.role == UserRole.TEACHER:
        return redirect('teacher:dashboard')
    school = get_school(request)
    school_class = get_object_or_404(SchoolClass, id=class_id, school=school, is_active=True)
    return render(request, 'schools/class_detail.html', {
        'school_class': school_class,
        'cockpit':      build_class_cockpit(school, school_class),
        'page_title':   school_class.name,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def class_create(request):
    school = get_school(request)

    form = SchoolClassForm(request.POST)
    if not form.is_valid():
        if request.htmx:
            return render(request, 'schools/partials/class_form_fields.html', {'form': form})
        return render(request, 'schools/class_list.html', {
            'form': form, 'school': school, 'classes': list(_classes_qs(school)),
        })

    cd = form.cleaned_data

    # Réactivation d'une classe soft-deletée de même nom (insensible casse ET
    # accents via normalisation Python), sinon création. cleaned_data → max_capacity
    # vide = None (pas de ValueError).
    target = norm_name(cd['name'])
    existing = next(
        (sc for sc in SchoolClass.objects.filter(school=school, is_active=False)
         if norm_name(sc.name) == target),
        None,
    )
    try:
        with transaction.atomic():
            if existing:
                existing.is_active    = True
                existing.name         = cd['name']      # rafraîchit la casse saisie
                existing.level        = cd['level']
                existing.annual_fee   = cd['annual_fee']
                existing.max_capacity = cd['max_capacity']
                existing.save()
                message = _('Classe réactivée avec succès.')
            else:
                school_class = form.save(commit=False)
                school_class.school = school
                school_class.save()
                message = _('Classe créée avec succès.')
    except IntegrityError:
        # Contrainte partielle unique_active_class_per_school (non validée par le
        # ModelForm) : un doublon ACTIF du même nom existe déjà.
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {
            'message': "Une classe avec ce nom existe déjà dans cet établissement.",
            'type': 'error',
        }})
        return resp

    # Réponse succès (HTMX : liste rafraîchie + toast ; sinon page complète).
    if request.htmx:
        classes = list(_classes_qs(school))
        resp = render(request, 'schools/partials/class_list_refresh.html', {
            'classes': classes,
            'form': SchoolClassForm(),
            'success_message': message,
            'cstats': compute_class_stats(classes),
        })
        resp['HX-Trigger'] = json.dumps({'close-add-modal': True, 'showToast': {'message': str(message), 'type': 'success'}})
        return resp

    return render(request, 'schools/class_list.html', {
        'form': SchoolClassForm(), 'school': school, 'classes': list(_classes_qs(school)),
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
@director_or_staff_required
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
    return render(request, 'schools/partials/class_table_body.html', {
        'classes': _filter_classes(request, school),
        'q':     request.GET.get('q', ''),
        'level': request.GET.get('level', ''),
        'dispo': request.GET.get('dispo', ''),
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
@director_or_staff_required
def class_import_template(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Classes'

    # En-têtes (* = obligatoire). Le parser lit par position, le renommage est sûr.
    headers = ['Nom de la classe *', 'Niveau *', 'Frais annuels FCFA *', 'Capacité max']
    ws.append(headers)
    header_fill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
    for col_idx, cell in enumerate(ws[1], start=1):
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[get_column_letter(col_idx)].width = 26

    # Lignes d'exemple réalistes (système éducatif malien). À remplacer par vos classes.
    ws.append(['1ère année A',   'Fondamental 1er Cycle',  75000,  50])
    ws.append(['6ème année',     'Fondamental 1er Cycle',  90000,  45])
    ws.append(['9ème année B',   'Fondamental 2ème Cycle', 120000, 40])
    ws.append(['11ème Sciences', 'Secondaire Général',     150000, 35])
    example_font = Font(italic=True, color='9CA3AF')
    for row in ws.iter_rows(min_row=2, max_row=5):
        for cell in row:
            cell.font = example_font

    # Feuille « Instructions » séparée (n'interfère pas avec l'import, qui ne lit
    # que la feuille active « Classes »).
    helpws = wb.create_sheet('Instructions')
    helpws.column_dimensions['A'].width = 40
    helpws.append(['Comment remplir ce modèle'])
    helpws['A1'].font = Font(bold=True, size=12, color='1E3A5F')
    helpws.append([''])
    helpws.append(['Colonnes obligatoires (*) : Nom de la classe, Niveau, Frais annuels FCFA'])
    helpws.append(['Colonne optionnelle : Capacité max (laisser vide si non gérée)'])
    helpws.append(['Frais annuels : montant en FCFA, chiffres uniquement (ex : 90000)'])
    helpws.append([''])
    helpws.append(['Valeurs acceptées pour la colonne « Niveau » :'])
    helpws['A7'].font = Font(bold=True, color='1E3A5F')
    for label in [
        'Préscolaire',
        'Fondamental 1er Cycle',
        'Fondamental 2ème Cycle',
        'Secondaire Général',
        'Secondaire Professionnel',
        'Enseignement Supérieur',
    ]:
        helpws.append([label])
    helpws.append([''])
    helpws.append(['Astuce : supprimez les 4 lignes d\'exemple avant d\'importer vos données.'])

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
@director_or_staff_required
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
@director_or_staff_required
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

    classes = list(_classes_qs(school))

    resp = render(request, 'schools/partials/class_list_refresh.html', {
        'classes': classes,
        'success_message': msg,
        'cstats': compute_class_stats(classes),
    })
    resp['HX-Trigger'] = json.dumps({'close-import-modal': True, 'showToast': {'message': msg, 'type': 'success'}})
    return resp


@login_required
@director_or_staff_required
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


# ─────────────────────────────────────────────────────────────────────
# ANNONCES
# ─────────────────────────────────────────────────────────────────────

@login_required
@director_or_staff_required
def announcement_list(request):
    school = get_school(request)
    announcements = (
        SchoolAnnouncement.objects
        .filter(school=school)
        .select_related('author', 'target_class', 'target_student')
        .order_by('-created_at')
    )
    classes = SchoolClass.objects.filter(school=school, is_active=True).order_by('name')
    from apps.students.models import Student
    students = (
        Student.objects
        .filter(school=school, is_active=True)
        .select_related('school_class')
        .order_by('full_name')
    )
    return render(request, 'schools/announcements/list.html', {
        'announcements': announcements,
        'classes':        classes,
        'students':       students,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def announcement_create(request):
    school   = get_school(request)
    title    = request.POST.get('title', '').strip()
    body     = request.POST.get('body', '').strip()
    audience = request.POST.get('audience', 'school')

    if not title:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Le titre est requis.', 'type': 'error'}})
        return resp
    if not body:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Le contenu est requis.', 'type': 'error'}})
        return resp
    if audience not in ('school', 'class', 'student'):
        audience = 'school'

    target_class   = None
    target_student = None

    if audience == 'class':
        class_id = request.POST.get('target_class_id', '').strip()
        if not class_id:
            resp = HttpResponse(status=422)
            resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Sélectionnez une classe.', 'type': 'error'}})
            return resp
        target_class = get_object_or_404(SchoolClass, id=class_id, school=school)

    if audience == 'student':
        student_id = request.POST.get('target_student_id', '').strip()
        if not student_id:
            resp = HttpResponse(status=422)
            resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Sélectionnez un élève.', 'type': 'error'}})
            return resp
        from apps.students.models import Student
        target_student = get_object_or_404(Student, id=student_id, school=school)

    ann = SchoolAnnouncement.objects.create(
        school=school,
        author=request.user,
        title=title,
        body=body,
        audience=audience,
        target_class=target_class,
        target_student=target_student,
    )

    resp = render(request, 'schools/announcements/partials/announcement_card.html', {'ann': ann})
    resp['HX-Trigger'] = json.dumps({
        'close-announcement-panel': True,
        'showToast': {'message': 'Brouillon créé.', 'type': 'success'},
    })
    return resp


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def announcement_publish(request, pk):
    from django.utils import timezone
    from apps.notifications.services import notify_bulk, notify_guardians
    from apps.notifications.models import NotificationCategory
    from apps.students.models import StudentGuardian

    school = get_school(request)
    ann    = get_object_or_404(SchoolAnnouncement, pk=pk, school=school)

    if ann.is_published:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Annonce déjà publiée.', 'type': 'error'}})
        return resp

    ann.is_published = True
    ann.published_at = timezone.now()
    ann.save(update_fields=['is_published', 'published_at'])

    notif_url  = reverse('parent:annonces')
    notif_body = ann.body[:150]

    if ann.audience == 'school':
        ids = list(
            StudentGuardian.objects
            .filter(student__school=school)
            .values_list('guardian_id', flat=True)
            .distinct()
        )
        notify_bulk(ids, school, NotificationCategory.INFO, ann.title, notif_body, notif_url, target=ann)

    elif ann.audience == 'class' and ann.target_class:
        ids = list(
            StudentGuardian.objects
            .filter(student__school_class=ann.target_class)
            .values_list('guardian_id', flat=True)
            .distinct()
        )
        notify_bulk(ids, school, NotificationCategory.INFO, ann.title, notif_body, notif_url, target=ann)

    elif ann.audience == 'student' and ann.target_student:
        notify_guardians(
            ann.target_student, NotificationCategory.INFO,
            ann.title, notif_body, notif_url, target=ann,
        )

    resp = render(request, 'schools/announcements/partials/announcement_card.html', {'ann': ann})
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Annonce publiée et envoyée.', 'type': 'success'}})
    return resp


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def announcement_delete(request, pk):
    school = get_school(request)
    ann    = get_object_or_404(SchoolAnnouncement, pk=pk, school=school)

    if ann.is_published:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Impossible de supprimer une annonce publiée.', 'type': 'error'}})
        return resp

    ann.delete()
    resp = HttpResponse('')
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Brouillon supprimé.', 'type': 'success'}})
    return resp
