import json
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import (
    AppearanceForm, GeneralSettingsForm,
    ReceiptModeForm, ReceiptUploadForm, ReceiptSignerForm,
    SchoolYearForm, PeriodForm, SubjectForm, ClassSubjectForm,
    BulletinConfigForm,
)
from .models import SchoolYear, Period, PeriodType, Subject, ClassSubject, Note, BulletinConfig
from apps.core.mixins import get_school

# Variables disponibles pour le mapping de reçu personnalisé
_RECEIPT_VARIABLES = [
    ('nom_eleve',       '{{nom_eleve}}'),
    ('classe',          '{{classe}}'),
    ('montant',         '{{montant}}'),
    ('date',            '{{date}}'),
    ('numero_recu',     '{{numero_recu}}'),
    ('solde',           '{{solde}}'),
    ('nom_ecole',       '{{nom_ecole}}'),
    ('telephone_ecole', '{{telephone_ecole}}'),
    ('mode_paiement',   '{{mode_paiement}}'),
    ('ignore',          '— Ignorer —'),
]

# Métadonnées des sections "coming soon"
_COMING_SOON_META = {
    'school-years':    ('Années scolaires',      'Gérez les années scolaires, archivez une année et initialisez la suivante.',             'calendar'),
    'payment-methods': ('Modes de paiement',     'Configurez les modes de paiement acceptés par votre établissement.',                    'credit-card'),
    'bulletin':        ('Modèle de bulletin',    'Personnalisez la mise en page des bulletins de notes PDF.',                             'document'),
    'headers':         ('En-têtes officiels',    'Définissez l\'en-tête officiel de l\'établissement pour les documents administratifs.', 'template'),
    'sms':             ('Notifications SMS',     'Envoyez des alertes automatiques aux parents par SMS.',                                 'chat'),
    'whatsapp':        ('Notifications WhatsApp','Communiquez avec les parents via WhatsApp Business.',                                   'phone'),
    'profile':         ('Mon profil',            'Modifiez vos informations personnelles et votre mot de passe.',                        'user'),
    'security':        ('Sécurité',              'Gérez les accès, les sessions actives et l\'authentification à deux facteurs.',         'lock'),
    'plan':            ('Plan et usage',         'Consultez votre forfait actuel, l\'usage et les options de mise à niveau.',             'chart'),
}


_SIGNER_SUGGESTIONS = ['Le Directeur', 'Le Caissier', 'Le Comptable', 'La Directrice']


def _custom_step(school):
    """Détermine l'étape courante du flux de reçu personnalisé."""
    if school.receipt_configured_at:
        return 'configured'
    if school.receipt_template_pdf:
        return 'uploaded'
    return 'empty'


def _receipt_ctx(school, **extra):
    """Contexte de base pour receipt_content.html."""
    return {
        'school': school,
        'custom_step': _custom_step(school),
        'signer_suggestions': _SIGNER_SUGGESTIONS,
        **extra,
    }


@login_required
def general(request):
    school = get_school(request)
    if request.method == 'POST':
        form = GeneralSettingsForm(request.POST, instance=school)
        if form.is_valid():
            form.save()
            resp = render(request, 'settings/partials/general_form.html', {
                'form': GeneralSettingsForm(instance=school),
                'school': school,
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Modifications enregistrées.', 'type': 'success'}}
            )
            return resp
        return render(request, 'settings/partials/general_form.html', {
            'form': form, 'school': school,
        })
    return render(request, 'settings/general.html', {
        'form': GeneralSettingsForm(instance=school),
        'school': school,
        'active_section': 'general',
    })


@login_required
def appearance(request):
    school = get_school(request)
    if request.method == 'POST':
        if request.POST.get('delete_logo'):
            if school.logo:
                school.logo.delete(save=True)
            school.refresh_from_db()
            resp = render(request, 'settings/partials/appearance_form.html', {
                'form': AppearanceForm(instance=school), 'school': school,
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Logo supprimé.', 'type': 'info'}}
            )
            return resp
        form = AppearanceForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            school.refresh_from_db()
            resp = render(request, 'settings/partials/appearance_form.html', {
                'form': AppearanceForm(instance=school), 'school': school,
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Apparence mise à jour.', 'type': 'success'}}
            )
            return resp
        return render(request, 'settings/partials/appearance_form.html', {
            'form': form, 'school': school,
        })
    return render(request, 'settings/appearance.html', {
        'form': AppearanceForm(instance=school),
        'school': school,
        'active_section': 'appearance',
    })


@login_required
def receipt(request):
    school = get_school(request)
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'set_mode':
            mode = request.POST.get('receipt_mode', 'standard')
            if mode in ('standard', 'custom'):
                school.receipt_mode = mode
                school.save(update_fields=['receipt_mode'])
            school.refresh_from_db()
            resp = render(request, 'settings/partials/receipt_content.html', _receipt_ctx(school))
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Mode mis à jour.', 'type': 'success'}}
            )
            return resp

        elif action == 'upload_pdf':
            form = ReceiptUploadForm(request.POST, request.FILES, instance=school)
            if form.is_valid():
                form.save()
                school.refresh_from_db()
                return render(request, 'settings/partials/receipt_content.html', _receipt_ctx(school))
            return render(request, 'settings/partials/receipt_content.html', _receipt_ctx(
                school, custom_step='empty',
                upload_error=form.errors.get('receipt_template_pdf', ['Erreur inconnue.'])[0],
            ))

        elif action == 'analyze':
            return render(request, 'settings/partials/receipt_content.html', _receipt_ctx(
                school, custom_step='mapping',
                mapping=[], variables=_RECEIPT_VARIABLES, analyze_notice=True,
            ))

        elif action == 'save_signer':
            form = ReceiptSignerForm(request.POST, instance=school)
            if form.is_valid():
                form.save()
                school.refresh_from_db()
                resp = render(request, 'settings/partials/receipt_content.html', _receipt_ctx(school))
                resp['HX-Trigger'] = json.dumps(
                    {'showToast': {'message': 'Titre du signataire enregistré.', 'type': 'success'}}
                )
                return resp
            return render(request, 'settings/partials/receipt_content.html', _receipt_ctx(school))

        elif action == 'save_mapping':
            mapping_data = {
                key[4:]: val
                for key, val in request.POST.items()
                if key.startswith('var_')
            }
            school.receipt_mapping = mapping_data
            school.receipt_configured_at = timezone.now()
            school.receipt_mode = 'custom'
            school.save(update_fields=['receipt_mapping', 'receipt_configured_at', 'receipt_mode'])
            school.refresh_from_db()
            resp = render(request, 'settings/partials/receipt_content.html', _receipt_ctx(school))
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Modèle de reçu configuré avec succès.', 'type': 'success'}}
            )
            return resp

    return render(request, 'settings/receipt.html', _receipt_ctx(school, active_section='receipt'))


@login_required
def bulletin(request):
    school = get_school(request)
    config, _ = BulletinConfig.objects.get_or_create(school=school)
    if request.method == 'POST':
        form = BulletinConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            resp = render(request, 'settings/partials/bulletin_form.html', {
                'form': BulletinConfigForm(instance=config),
                'config': config,
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Paramètres bulletin enregistrés.', 'type': 'success'}}
            )
            return resp
        return render(request, 'settings/partials/bulletin_form.html', {
            'form': form, 'config': config,
        })
    return render(request, 'settings/bulletin.html', {
        'form': BulletinConfigForm(instance=config),
        'config': config,
        'active_section': 'bulletin',
    })


# ─────────────────────────────────────────────────────────────
# Années scolaires
# ─────────────────────────────────────────────────────────────

@login_required
def school_years(request):
    school = get_school(request)
    years  = (
        SchoolYear.objects
        .filter(school=school)
        .annotate(periods_count=Count('periods'))
        .order_by('-start_date')
    )
    current_year = date.today().year
    suggested    = f'{current_year}-{current_year + 1}'
    form         = SchoolYearForm(initial={'name': suggested})
    return render(request, 'settings/school_years.html', {
        'years':          years,
        'form':           form,
        'active_section': 'school-years',
        'school':         school,
    })


@login_required
@require_http_methods(['POST'])
def school_year_create(request):
    school = get_school(request)
    form   = SchoolYearForm(request.POST)
    if form.is_valid():
        year        = form.save(commit=False)
        year.school = school
        try:
            year.full_clean()
        except ValidationError as e:
            form.add_error(None, e)
        else:
            year.save()
            years = (
                SchoolYear.objects
                .filter(school=school)
                .annotate(periods_count=Count('periods'))
            )
            current_year = date.today().year
            suggested    = f'{current_year}-{current_year + 1}'
            empty_form   = SchoolYearForm(initial={'name': suggested})
            # Contenu OOB pour rafraîchir la liste
            list_html = render_to_string(
                'settings/partials/school_year_list.html',
                {'years': years}, request=request,
            )
            oob = f'<div id="school-year-list" hx-swap-oob="true">{list_html}</div>'
            form_html = render_to_string(
                'settings/partials/school_year_form.html',
                {'form': empty_form}, request=request,
            )
            resp = HttpResponse(form_html + oob)
            resp['HX-Trigger'] = json.dumps({
                'showToast':        {'message': 'Année scolaire créée.', 'type': 'success'},
                'schoolYearSaved':  {},
            })
            return resp
    return render(request, 'settings/partials/school_year_form.html', {'form': form})


@login_required
@require_http_methods(['POST'])
def school_year_toggle(request, year_id):
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)
    action = request.POST.get('action', 'activate')

    if action == 'archive':
        year.is_active = False
        year.save(update_fields=['is_active'])
        msg = f'Année {year.name} archivée.'
    else:
        year.is_active = True
        try:
            year.full_clean()
            year.save(update_fields=['is_active'])
            msg = f'Année {year.name} activée.'
        except ValidationError as e:
            year.is_active = False
            years = (
                SchoolYear.objects
                .filter(school=school)
                .annotate(periods_count=Count('periods'))
            )
            resp = render(request, 'settings/partials/school_year_list.html', {
                'years': years, 'error': str(e.message),
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': str(e.message), 'type': 'error'}}
            )
            return resp

    years = (
        SchoolYear.objects
        .filter(school=school)
        .annotate(periods_count=Count('periods'))
    )
    resp = render(request, 'settings/partials/school_year_list.html', {'years': years})
    resp['HX-Trigger'] = json.dumps(
        {'showToast': {'message': msg, 'type': 'info'}}
    )
    return resp


# ─────────────────────────────────────────────────────────────
# Périodes
# ─────────────────────────────────────────────────────────────

@login_required
def school_year_periods(request, year_id):
    school  = get_school(request)
    year    = get_object_or_404(SchoolYear, id=year_id, school=school)
    periods = year.periods.order_by('order')
    form    = PeriodForm(initial={'start_date': year.start_date, 'end_date': year.end_date, 'order': periods.count() + 1})
    return render(request, 'settings/school_year_periods.html', {
        'year':           year,
        'periods':        periods,
        'form':           form,
        'active_section': 'school-years',
        'school':         school,
    })


@login_required
@require_http_methods(['POST'])
def period_generate(request, year_id):
    """Génère automatiquement les périodes depuis un template prédéfini."""
    school   = get_school(request)
    year     = get_object_or_404(SchoolYear, id=year_id, school=school)
    template = request.POST.get('template')

    if template == '3trimesters':
        configs = [
            ('Trimestre 1', PeriodType.TRIMESTER, 1),
            ('Trimestre 2', PeriodType.TRIMESTER, 2),
            ('Trimestre 3', PeriodType.TRIMESTER, 3),
        ]
    elif template == '2semesters':
        configs = [
            ('Semestre 1', PeriodType.SEMESTER, 1),
            ('Semestre 2', PeriodType.SEMESTER, 2),
        ]
    else:
        return HttpResponse(status=400)

    # Supprimer les périodes existantes avant génération
    periods_with_notes = year.periods.filter(grade_notes__isnull=False).distinct()
    if periods_with_notes.exists():
        return HttpResponse(
            '<div class="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">'
            '<p class="font-medium">Impossible de régénérer les périodes.</p>'
            '<p>Des notes existent déjà sur certaines périodes. Supprimez les notes d\'abord.</p>'
            '</div>',
            status=422
        )
    year.periods.all().delete()

    n         = len(configs)
    total_days = (year.end_date - year.start_date).days
    segment   = total_days // n
    current   = year.start_date

    for i, (name, ptype, order) in enumerate(configs):
        is_last = (i == n - 1)
        end     = year.end_date if is_last else current + timedelta(days=segment - 1)
        Period.objects.create(
            school_year=year, name=name, period_type=ptype,
            start_date=current, end_date=end, order=order,
        )
        current = end + timedelta(days=1)

    periods = year.periods.order_by('order')
    resp    = render(request, 'settings/partials/periods_list.html', {
        'year': year, 'periods': periods,
    })
    resp['HX-Trigger'] = json.dumps(
        {'showToast': {'message': f'{n} périodes générées.', 'type': 'success'}}
    )
    return resp


@login_required
@require_http_methods(['POST'])
def period_create(request, year_id):
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)
    form   = PeriodForm(request.POST)
    if form.is_valid():
        period             = form.save(commit=False)
        period.school_year = year
        period.save()
        periods = year.periods.order_by('order')
        empty_form = PeriodForm(initial={'order': periods.count() + 1})
        list_html = render_to_string(
            'settings/partials/periods_list.html',
            {'year': year, 'periods': periods}, request=request,
        )
        oob      = f'<div id="periods-list" hx-swap-oob="true">{list_html}</div>'
        form_html = render_to_string(
            'settings/partials/period_form.html',
            {'form': empty_form, 'year': year}, request=request,
        )
        resp = HttpResponse(form_html + oob)
        resp['HX-Trigger'] = json.dumps(
            {'showToast': {'message': 'Période ajoutée.', 'type': 'success'}}
        )
        return resp
    return render(request, 'settings/partials/period_form.html', {'form': form, 'year': year})


@login_required
@require_http_methods(['POST'])
def period_toggle_notes(request, period_id):
    school          = get_school(request)
    period          = get_object_or_404(Period, id=period_id, school_year__school=school)
    period.is_notes_open = not period.is_notes_open
    period.save(update_fields=['is_notes_open'])
    return render(request, 'settings/partials/period_card.html', {
        'period': period, 'year': period.school_year,
    })


@login_required
@require_http_methods(['DELETE'])
def period_delete(request, period_id):
    school = get_school(request)
    period = get_object_or_404(Period, id=period_id, school_year__school=school)
    year   = period.school_year
    note_count = Note.objects.filter(period=period).count()
    if note_count > 0:
        response = HttpResponse(status=422)
        response['HX-Trigger'] = json.dumps({
            'showToast': {
                'message': f'Impossible de supprimer cette période : {note_count} note(s) saisie(s). Supprimez les notes d\'abord.',
                'type': 'error',
            }
        })
        return response
    period.delete()
    periods = year.periods.order_by('order')
    resp    = render(request, 'settings/partials/periods_list.html', {
        'year': year, 'periods': periods,
    })
    resp['HX-Trigger'] = json.dumps(
        {'showToast': {'message': 'Période supprimée.', 'type': 'info'}}
    )
    return resp


# ─────────────────────────────────────────────────────────────
# Matières
# ─────────────────────────────────────────────────────────────

# Suggestions rapides prédéfinies : (nom complet, abréviation)
_QUICK_SUBJECTS = [
    ('Mathématiques', 'Maths'),
    ('Français', 'Fr.'),
    ('Arabe', 'Arabe'),
    ('Sciences', 'SVT'),
    ('Histoire-Géo', 'Hist.'),
    ('Anglais', 'Angl.'),
    ('EPS', 'EPS'),
    ('Informatique', 'Info'),
    ('Fiqh', 'Fiqh'),
    ('Physique-Chimie', 'PC'),
]


@login_required
def subjects(request):
    school     = get_school(request)
    subj_list  = Subject.objects.filter(school=school, is_active=True)
    classes    = school.classes.filter(is_active=True).order_by('level', 'name')
    form       = SubjectForm()
    return render(request, 'settings/subjects.html', {
        'subjects':       subj_list,
        'classes':        classes,
        'form':           form,
        'quick_subjects': _QUICK_SUBJECTS,
        'active_section': 'subjects',
        'school':         school,
    })


@login_required
@require_http_methods(['POST'])
def subject_create(request):
    school = get_school(request)
    form   = SubjectForm(request.POST)
    if form.is_valid():
        subj        = form.save(commit=False)
        subj.school = school
        try:
            subj.validate_unique()
        except ValidationError as e:
            form.add_error(None, e)
        else:
            subj.save()
            subj_list = Subject.objects.filter(school=school, is_active=True)
            list_html = render_to_string(
                'settings/partials/subject_list.html',
                {'subjects': subj_list}, request=request,
            )
            oob       = f'<div id="subject-list" hx-swap-oob="true">{list_html}</div>'
            form_html = render_to_string(
                'settings/partials/subject_form.html',
                {'form': SubjectForm()}, request=request,
            )
            resp = HttpResponse(form_html + oob)
            resp['HX-Trigger'] = json.dumps({
                'showToast':     {'message': 'Matière créée.', 'type': 'success'},
                'subjectSaved':  {},
            })
            return resp
    return render(request, 'settings/partials/subject_form.html', {'form': form})


@login_required
@require_http_methods(['DELETE'])
def subject_delete(request, subject_id):
    school  = get_school(request)
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    subject.is_active = False
    subject.save(update_fields=['is_active'])
    subj_list = Subject.objects.filter(school=school, is_active=True)
    resp      = render(request, 'settings/partials/subject_list.html', {'subjects': subj_list})
    resp['HX-Trigger'] = json.dumps(
        {'showToast': {'message': 'Matière supprimée.', 'type': 'info'}}
    )
    return resp


# ─────────────────────────────────────────────────────────────
# Matières par classe
# ─────────────────────────────────────────────────────────────

def _class_subjects_ctx(school, school_class):
    """Contexte commun pour le panneau matières d'une classe."""
    from apps.accounts.models import User, UserRole
    class_subjects = (
        ClassSubject.objects
        .filter(school_class=school_class, is_active=True)
        .select_related('subject', 'teacher')
        .order_by('order', 'subject__name')
    )
    assigned_ids = class_subjects.values_list('subject_id', flat=True)
    available    = Subject.objects.filter(school=school, is_active=True).exclude(id__in=assigned_ids)
    teachers     = User.objects.filter(
        school=school, is_active=True,
        role=UserRole.TEACHER,
    ).order_by('full_name')
    return {
        'school_class':       school_class,
        'class_subjects':     class_subjects,
        'available_subjects': available,
        'teachers':           teachers,
    }


@login_required
def class_subjects_panel(request, class_id):
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), id=class_id)
    return render(request, 'settings/partials/class_subjects.html',
                  _class_subjects_ctx(school, school_class))


@login_required
def class_subjects_search(request):
    """Répond aux requêtes HTMX du select de classe (GET ?class_id=X)."""
    class_id = request.GET.get('class_id', '').strip()
    if not class_id:
        return HttpResponse(
            '<div class="text-center py-10 text-gray-400 text-sm">'
            'Sélectionnez une classe pour gérer ses matières.</div>'
        )
    school = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), id=class_id)
    return render(request, 'settings/partials/class_subjects.html',
                  _class_subjects_ctx(school, school_class))


@login_required
@require_http_methods(['POST'])
def class_subject_add(request, class_id):
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), id=class_id)
    form         = ClassSubjectForm(school, school_class, request.POST)
    if form.is_valid():
        cs              = form.save(commit=False)
        cs.school_class = school_class
        cs.save()
        resp = render(request, 'settings/partials/class_subjects.html',
                      _class_subjects_ctx(school, school_class))
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Matière ajoutée à la classe.', 'type': 'success'}})
        return resp
    return render(request, 'settings/partials/class_subjects.html',
                  _class_subjects_ctx(school, school_class))


@login_required
@require_http_methods(['POST'])
def class_subject_update(request, cs_id):
    school = get_school(request)
    cs     = get_object_or_404(
        ClassSubject.objects.select_related('school_class'),
        id=cs_id, school_class__school=school,
    )
    form = ClassSubjectForm(school, cs.school_class, request.POST, instance=cs)
    if form.is_valid():
        form.save()
        resp = render(request, 'settings/partials/class_subjects.html',
                      _class_subjects_ctx(school, cs.school_class))
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Matière mise à jour.', 'type': 'success'}})
        return resp
    return render(request, 'settings/partials/class_subjects.html',
                  _class_subjects_ctx(school, cs.school_class))


@login_required
@require_http_methods(['DELETE'])
def class_subject_remove(request, cs_id):
    school = get_school(request)
    cs     = get_object_or_404(
        ClassSubject.objects.select_related('school_class'),
        id=cs_id, school_class__school=school,
    )
    school_class = cs.school_class
    try:
        cs.delete()
    except ProtectedError:
        return HttpResponse(
            '<div class="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">'
            '<p class="font-medium">Impossible de retirer cette matière.</p>'
            '<p>Des notes ont été saisies pour cette matière dans cette classe. Supprimez les notes d\'abord.</p>'
            '</div>',
            status=422
        )
    return render(request, 'settings/partials/class_subjects.html',
                  _class_subjects_ctx(school, school_class))


@login_required
def coming_soon(request, section):
    title, description, icon = _COMING_SOON_META.get(
        section, ('Section', 'Cette section sera disponible prochainement.', 'document'),
    )
    return render(request, 'settings/coming_soon.html', {
        'active_section': section,
        'section_title':  title,
        'section_desc':   description,
        'section_icon':   icon,
        'school':         get_school(request),
    })
