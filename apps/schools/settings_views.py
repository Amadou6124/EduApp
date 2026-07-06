import json
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction, models
from django.db.models import Count, Q, ProtectedError
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from .forms import (
    AppearanceForm, GeneralSettingsForm,
    ReceiptSignerForm,
    SchoolYearForm, PeriodForm, SubjectForm, ClassSubjectForm,
    BulletinConfigForm,
)
from .models import (
    SchoolYear, Period, PeriodType, EducationLevel, SchoolClass,
    Subject, ClassSubject, Note, BulletinConfig, AppreciationScale,
)
from apps.core.mixins import get_school, director_or_staff_required

# ── Module Finances (Lot 2) — catalogue de frais ───────────────────────────────
from apps.finance.models import (
    FeeType, FeeVariant, PaymentScheduleTemplate, FeeCategory,
)
from apps.finance.forms import FeeTypeForm, FeeVariantForm

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


def _receipt_ctx(school, **extra):
    """Contexte de base pour receipt_content.html."""
    return {
        'school': school,
        'signer_suggestions': _SIGNER_SUGGESTIONS,
        **extra,
    }


@login_required
@director_or_staff_required
def settings_home(request):
    """Index des paramètres — liste drill-in sur mobile, repère sur desktop."""
    school = get_school(request)
    return render(request, 'settings/index.html', {
        'school': school, 'active_section': 'home',
    })


@login_required
@director_or_staff_required
def general(request):
    school = get_school(request)
    if request.method == 'POST':
        # Suppression du logo (depuis la carte Identité)
        if request.POST.get('delete_logo'):
            if school.logo:
                school.logo.delete(save=True)
            school.refresh_from_db()
            resp = render(request, 'settings/partials/general_form.html', {
                'form': GeneralSettingsForm(instance=school), 'school': school,
            })
            resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Logo supprimé.', 'type': 'info'}})
            return resp

        # Enregistrement automatique du logo dès la sélection (indépendant des autres champs)
        if request.POST.get('logo_only'):
            logo = request.FILES.get('logo')
            err = None
            if not logo:
                err = "Aucun fichier reçu."
            elif getattr(logo, 'content_type', '') not in ('image/jpeg', 'image/png', 'image/svg+xml', 'image/webp'):
                err = "Format invalide. Utilisez PNG, JPG ou SVG."
            elif logo.size > 2 * 1024 * 1024:
                err = "Le logo ne doit pas dépasser 2 Mo."
            if err:
                resp = render(request, 'settings/partials/general_form.html', {
                    'form': GeneralSettingsForm(instance=school), 'school': school,
                })
                resp['HX-Trigger'] = json.dumps({'showToast': {'message': err, 'type': 'error'}})
                return resp
            school.logo = logo
            school.save()
            school.refresh_from_db()
            resp = render(request, 'settings/partials/general_form.html', {
                'form': GeneralSettingsForm(instance=school), 'school': school,
            })
            resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Logo enregistré.', 'type': 'success'}})
            return resp

        form = GeneralSettingsForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            school.refresh_from_db()
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
@director_or_staff_required
def receipt(request):
    school = get_school(request)
    if request.method == 'POST' and request.POST.get('action') == 'save_signer':
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

    return render(request, 'settings/receipt.html', _receipt_ctx(school, active_section='receipt'))


@login_required
@director_or_staff_required
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
        'scales': AppreciationScale.objects.filter(school=school).order_by('-min_grade'),
        'active_section': 'bulletin',
    })


# ─────────────────────────────────────────────────────────────
# Barème d'appréciations (note → mention)
# ─────────────────────────────────────────────────────────────

_DEFAULT_APPRECIATIONS = [
    ('18', 'Excellent'),
    ('16', 'Très bien'),
    ('14', 'Bien'),
    ('12', 'Assez bien'),
    ('10', 'Passable'),
    ('8',  'Insuffisant'),
    ('0',  'Faible'),
]


def _render_scales(request, school, message=None, msg_type='success'):
    scales = AppreciationScale.objects.filter(school=school).order_by('-min_grade')
    resp = render(request, 'settings/partials/appreciation_scale.html', {'scales': scales})
    if message:
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': msg_type}})
    return resp


def _parse_grade(raw):
    from decimal import Decimal, InvalidOperation
    try:
        g = Decimal((raw or '').strip().replace(',', '.'))
    except (InvalidOperation, TypeError):
        return None
    return g if g >= 0 else None


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def appreciation_add(request):
    school = get_school(request)
    label  = (request.POST.get('label') or '').strip()
    grade  = _parse_grade(request.POST.get('min_grade'))
    if not label or grade is None:
        return _render_scales(request, school, 'Libellé et note valide requis.', 'error')
    if AppreciationScale.objects.filter(school=school, label=label).exists():
        return _render_scales(request, school, 'Cette mention existe déjà.', 'error')
    AppreciationScale.objects.create(school=school, label=label, min_grade=grade)
    return _render_scales(request, school, 'Mention ajoutée.')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def appreciation_update(request, scale_id):
    school = get_school(request)
    scale  = get_object_or_404(AppreciationScale, id=scale_id, school=school)
    label  = (request.POST.get('label') or '').strip()
    grade  = _parse_grade(request.POST.get('min_grade'))
    if not label or grade is None:
        return _render_scales(request, school, 'Libellé et note valide requis.', 'error')
    if AppreciationScale.objects.filter(school=school, label=label).exclude(id=scale.id).exists():
        return _render_scales(request, school, 'Cette mention existe déjà.', 'error')
    scale.label = label
    scale.min_grade = grade
    scale.save(update_fields=['label', 'min_grade'])
    return _render_scales(request, school, 'Mention mise à jour.')


@login_required
@director_or_staff_required
@require_http_methods(['DELETE'])
def appreciation_delete(request, scale_id):
    school = get_school(request)
    AppreciationScale.objects.filter(id=scale_id, school=school).delete()
    return _render_scales(request, school, 'Mention supprimée.', 'info')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def appreciation_seed(request):
    school = get_school(request)
    for grade, label in _DEFAULT_APPRECIATIONS:
        AppreciationScale.objects.get_or_create(
            school=school, label=label, defaults={'min_grade': grade},
        )
    return _render_scales(request, school, 'Barème par défaut chargé.')


# ─────────────────────────────────────────────────────────────
# Années scolaires
# ─────────────────────────────────────────────────────────────

@login_required
@director_or_staff_required
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
@director_or_staff_required
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


def _year_list_response(request, school, message, msg_type='success'):
    years = (
        SchoolYear.objects
        .filter(school=school)
        .annotate(periods_count=Count('periods'))
    )
    resp = render(request, 'settings/partials/school_year_list.html', {'years': years})
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': msg_type}})
    return resp


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def school_year_update(request, year_id):
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)
    was_active = year.is_active
    form   = SchoolYearForm(request.POST, instance=year)

    def _toast_error(message):
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': 'error'}})
        return resp

    if not form.is_valid():
        return _toast_error(next(iter(form.errors.values()))[0])

    obj = form.save(commit=False)
    obj.is_active = was_active   # is_active géré par le toggle dédié, pas par l'édition
    try:
        obj.full_clean()
    except ValidationError as e:
        return _toast_error(str(getattr(e, 'message', e)))
    obj.save()
    return _year_list_response(request, school, 'Année scolaire modifiée.')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def school_year_delete(request, year_id):
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)

    # Garde : Period.school_year est CASCADE → ne jamais supprimer une année qui a
    # des périodes (perte silencieuse notes/bulletins) ou des inscriptions (PROTECT).
    if year.periods.exists() or year.enrollments.exists():
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {
            'message': "Année utilisée (périodes ou inscriptions) — suppression impossible. Archivez-la plutôt.",
            'type': 'error',
        }})
        return resp

    name = year.name
    try:
        with transaction.atomic():
            year.delete()
    except ProtectedError:
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {
            'message': "Année utilisée — suppression impossible. Archivez-la plutôt.",
            'type': 'error',
        }})
        return resp

    return _year_list_response(request, school, f'Année {name} supprimée.')


@login_required
@director_or_staff_required
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

# Ordre d'affichage des cycles (préscolaire → supérieur).
_CYCLE_ORDER = [
    EducationLevel.PRESCOLAIRE, EducationLevel.FONDAMENTAL_1, EducationLevel.FONDAMENTAL_2,
    EducationLevel.SECONDAIRE_GEN, EducationLevel.SECONDAIRE_PRO, EducationLevel.SUPERIEUR,
]
# Rythme choisi à la génération → (type de période, préfixe de nom).
_RYTHME_MAP = {
    'composition': (PeriodType.COMPOSITION, 'Composition'),
    'trimester':   (PeriodType.TRIMESTER,   'Trimestre'),
    'semester':    (PeriodType.SEMESTER,    'Semestre'),
}


def _period_sections(school, year):
    """Contexte des périodes : sections par cycle, périodes « toute l'école »
    (legacy), classes personnalisées (surcharge, Étape B) et classes encore
    personnalisables. Renvoie un dict prêt pour le template."""
    used   = set(SchoolClass.objects.filter(school=school).values_list('level', flat=True))
    labels = dict(EducationLevel.choices)
    all_periods = list(year.periods.select_related('school_class').order_by('order'))

    # Sections par cycle — HORS surcharges de classe.
    sections = []
    for cyc in _CYCLE_ORDER:
        if cyc in used:
            sections.append({
                'value':       cyc,
                'label':       labels.get(cyc, cyc),
                'class_count': SchoolClass.objects.filter(school=school, level=cyc).count(),
                'periods':     [p for p in all_periods
                                if p.education_level == cyc and p.school_class_id is None],
            })
    legacy = [p for p in all_periods if p.education_level is None and p.school_class_id is None]

    # Surcharges par classe (Étape B).
    by_class = {}
    for p in all_periods:
        if p.school_class_id:
            by_class.setdefault(p.school_class_id, []).append(p)
    custom_classes = [
        {'class': sc, 'cycle_label': labels.get(sc.level, sc.level), 'periods': by_class[sc.pk]}
        for sc in SchoolClass.objects.filter(school=school, pk__in=by_class.keys())
                                     .order_by('level', 'name')
    ]
    # Classes encore personnalisables (sans périodes propres) — pour le sélecteur.
    customizable = [
        {'class': sc, 'cycle_label': labels.get(sc.level, sc.level)}
        for sc in SchoolClass.objects.filter(school=school, is_active=True)
                                     .exclude(pk__in=by_class.keys())
                                     .order_by('level', 'name')
    ]
    return {
        'sections':             sections,
        'legacy_periods':       legacy,
        'custom_classes':       custom_classes,
        'customizable_classes': customizable,
    }


def _render_period_sections(request, school, year, toast=None, status=200):
    """Rend le bloc de sections groupées (réponse HTMX après génération/CRUD)."""
    ctx = _period_sections(school, year)
    ctx['year'] = year
    html = render_to_string('settings/partials/periods_grouped.html', ctx, request=request)
    resp = HttpResponse(html, status=status)
    if toast:
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': toast, 'type': 'success'}})
    return resp


@login_required
@director_or_staff_required
def school_year_periods(request, year_id):
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)
    ctx = _period_sections(school, year)
    ctx.update({
        'year':           year,
        'form':           PeriodForm(initial={'order': 1}),
        'active_section': 'school-years',
        'school':         school,
    })
    return render(request, 'settings/school_year_periods.html', ctx)


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def period_generate(request, year_id):
    """Génère les périodes d'UN cycle (compositions / trimestres…), dates optionnelles.

    Ne supprime QUE les périodes du cycle visé (garde-fou : bloqué si des notes
    y sont déjà saisies). Les dates ne sont posées que si `with_dates` est coché
    ET si l'année est datée — sinon les périodes naissent sans dates.
    """
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)

    class_id   = request.POST.get('class_id')
    cycle      = request.POST.get('cycle') or None      # '' → toute l'école
    rythme     = request.POST.get('rythme', 'trimester')
    with_dates = request.POST.get('with_dates') in ('on', 'true', '1', 'yes')
    try:
        count = int(request.POST.get('count', 0))
    except (TypeError, ValueError):
        count = 0

    if rythme not in _RYTHME_MAP or not (1 <= count <= 12):
        return HttpResponse(status=400)
    ptype, prefix = _RYTHME_MAP[rythme]

    # Cible : une CLASSE précise (surcharge) OU un cycle OU toute l'école.
    school_class = None
    if class_id:
        school_class = get_object_or_404(SchoolClass, pk=class_id, school=school)
        existing = year.periods.filter(school_class=school_class)
        scope_label = 'cette classe'
    elif cycle:
        existing = year.periods.filter(education_level=cycle, school_class__isnull=True)
        scope_label = 'ce cycle'
    else:
        existing = year.periods.filter(education_level__isnull=True, school_class__isnull=True)
        scope_label = 'ces périodes'

    # Garde-fou : notes déjà saisies → on bloque la régénération.
    if existing.filter(notes__isnull=False).exists():
        return HttpResponse(
            '<div class="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">'
            f'<p class="font-medium">Impossible de régénérer {scope_label}.</p>'
            '<p>Des notes existent déjà sur ses périodes. Supprimez les notes d\'abord.</p>'
            '</div>',
            status=422,
        )
    existing.delete()

    # Découpage des dates seulement si demandé ET si l'année est datée.
    dated   = bool(with_dates and year.start_date and year.end_date)
    segment = (year.end_date - year.start_date).days // count if dated else 0
    current = year.start_date

    for i in range(count):
        if dated:
            is_last = (i == count - 1)
            start   = current
            end     = year.end_date if is_last else current + timedelta(days=max(segment - 1, 0))
            current = end + timedelta(days=1)
        else:
            start = end = None
        Period.objects.create(
            school_year=year,
            education_level=(None if school_class else cycle),
            school_class=school_class,
            name=f'{prefix} {i + 1}', period_type=ptype,
            start_date=start, end_date=end, order=i + 1,
        )

    return _render_period_sections(request, school, year, toast=f'{count} périodes générées.')


@login_required
@director_or_staff_required
@require_http_methods(['POST', 'DELETE'])
def period_class_reset(request, year_id, class_id):
    """« Revenir au cycle » : supprime les périodes propres d'une classe → elle
    réhérite du rythme de son cycle. Bloqué si des notes y existent déjà."""
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=school)

    own = year.periods.filter(school_class=school_class)
    if own.filter(notes__isnull=False).exists():
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {
            'message': "Impossible : des notes existent sur les périodes propres de "
                       "cette classe. Supprimez-les d'abord.",
            'type': 'error',
        }})
        return resp
    own.delete()
    return _render_period_sections(
        request, school, year, toast=f'{school_class.name} suit de nouveau son cycle.',
    )


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def period_create(request, year_id):
    school = get_school(request)
    year   = get_object_or_404(SchoolYear, id=year_id, school=school)
    form   = PeriodForm(request.POST)
    if form.is_valid():
        period             = form.save(commit=False)
        period.school_year = year
        period.save()
        empty_form = PeriodForm(initial={'order': 1})
        list_ctx = _period_sections(school, year)
        list_ctx['year'] = year
        list_html = render_to_string(
            'settings/partials/periods_grouped.html', list_ctx, request=request,
        )
        oob       = f'<div id="periods-list" hx-swap-oob="true">{list_html}</div>'
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
@director_or_staff_required
@require_http_methods(['POST'])
def period_update(request, period_id):
    school = get_school(request)
    period = get_object_or_404(Period, id=period_id, school_year__school=school)
    form   = PeriodForm(request.POST, instance=period)

    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': first, 'type': 'error'}})
        return resp

    form.save()
    return _render_period_sections(request, school, period.school_year, toast='Période modifiée.')


@login_required
@director_or_staff_required
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
@director_or_staff_required
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
    return _render_period_sections(request, school, year, toast='Période supprimée.')


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
@director_or_staff_required
def subjects(request):
    school     = get_school(request)
    subj_list  = Subject.objects.filter(school=school, is_active=True)
    classes    = (
        school.classes.filter(is_active=True)
        .annotate(cs_count=Count('class_subjects', filter=Q(class_subjects__is_active=True)))
        .order_by('level', 'name')
    )
    active_class = classes.first()
    ctx = {
        'subjects':       subj_list,
        'classes':        classes,
        'form':           SubjectForm(),
        'quick_subjects': _QUICK_SUBJECTS,
        'active_section': 'subjects',
        'school':         school,
        'active_class':   active_class,
    }
    if active_class:
        ctx.update(_class_subjects_ctx(school, active_class))
    return render(request, 'settings/subjects.html', ctx)


@login_required
@director_or_staff_required
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
@director_or_staff_required
@require_http_methods(['POST'])
def subject_update(request, subject_id):
    school  = get_school(request)
    subject = get_object_or_404(Subject, id=subject_id, school=school, is_active=True)
    form    = SubjectForm(request.POST, instance=subject)

    def _toast_error(message):
        resp = HttpResponse(status=422)
        resp['HX-Trigger'] = json.dumps({'showToast': {'message': message, 'type': 'error'}})
        return resp

    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        return _toast_error(first)

    try:
        with transaction.atomic():
            form.save()
    except IntegrityError:
        # Contrainte partielle unique_active_subject_per_school (non validée par
        # le ModelForm) : une autre matière active porte déjà ce nom.
        return _toast_error('Une matière active porte déjà ce nom.')

    subj_list = Subject.objects.filter(school=school, is_active=True)
    resp = render(request, 'settings/partials/subject_list.html', {'subjects': subj_list})
    resp['HX-Trigger'] = json.dumps({'showToast': {'message': 'Matière modifiée.', 'type': 'success'}})
    return resp


@login_required
@director_or_staff_required
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
    other_classes = (
        school.classes.filter(is_active=True)
        .exclude(pk=school_class.pk)
        .annotate(cs_count=Count('class_subjects', filter=Q(class_subjects__is_active=True)))
        .filter(cs_count__gt=0)
        .order_by('level', 'name')
    )
    return {
        'school_class':       school_class,
        'class_subjects':     class_subjects,
        'available_subjects': available,
        'teachers':           teachers,
        'other_classes':      other_classes,
    }


@login_required
@director_or_staff_required
def class_subjects_panel(request, class_id):
    school       = get_school(request)
    school_class = get_object_or_404(school.classes.filter(is_active=True), id=class_id)
    return render(request, 'settings/partials/class_subjects.html',
                  _class_subjects_ctx(school, school_class))


@login_required
@director_or_staff_required
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
@director_or_staff_required
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
@director_or_staff_required
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
@director_or_staff_required
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


def _copy_class_config(source_class, target_class):
    """Copie les matières (coeff, note max, durée — SANS enseignant) de source vers
    target. Upsert : crée les manquantes, met à jour les existantes. Ne supprime rien."""
    if source_class.pk == target_class.pk:
        return 0, 0
    existing = {cs.subject_id: cs for cs in ClassSubject.objects.filter(school_class=target_class)}
    created = updated = 0
    for s in ClassSubject.objects.filter(school_class=source_class, is_active=True):
        tgt = existing.get(s.subject_id)
        if tgt:
            tgt.coefficient, tgt.max_grade, tgt.duration_hours, tgt.is_active = (
                s.coefficient, s.max_grade, s.duration_hours, True)
            tgt.save(update_fields=['coefficient', 'max_grade', 'duration_hours', 'is_active'])
            updated += 1
        else:
            ClassSubject.objects.create(
                school_class=target_class, subject_id=s.subject_id,
                coefficient=s.coefficient, max_grade=s.max_grade,
                duration_hours=s.duration_hours, order=s.order,
            )
            created += 1
    return created, updated


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def class_subject_copy(request, class_id):
    """M3 — copie la config d'une autre classe vers celle-ci."""
    school = get_school(request)
    target = get_object_or_404(school.classes.filter(is_active=True), id=class_id)
    source = get_object_or_404(school.classes.filter(is_active=True), id=request.POST.get('source_class_id', ''))
    created, updated = _copy_class_config(source, target)
    resp = render(request, 'settings/partials/class_subjects.html', _class_subjects_ctx(school, target))
    resp['HX-Trigger'] = json.dumps({'showToast': {
        'message': f'Depuis {source.name} : {created} ajoutée(s), {updated} mise(s) à jour.', 'type': 'success'}})
    return resp


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def class_subject_bulk(request):
    """M4 — actions groupées sur plusieurs classes cochées : copier une config OU
    ajouter une matière."""
    from decimal import Decimal, InvalidOperation
    school  = get_school(request)
    ids     = [x for x in (request.POST.get('class_ids') or '').split(',') if x.strip()] \
              or request.POST.getlist('class_ids')
    targets = list(school.classes.filter(is_active=True, id__in=ids))
    action  = request.POST.get('action')
    if not targets:
        return _toast(HttpResponse(status=422), 'Aucune classe sélectionnée.', 'error')

    if action == 'copy':
        source = get_object_or_404(school.classes.filter(is_active=True), id=request.POST.get('source_class_id', ''))
        n = sum(1 for t in targets if t.pk != source.pk and _copy_class_config(source, t) is not None)
        msg = f'Config de {source.name} copiée vers {n} classe(s).'
    elif action == 'add':
        subject = get_object_or_404(Subject, id=request.POST.get('subject_id', ''), school=school, is_active=True)
        try:
            coeff = Decimal((request.POST.get('coefficient') or '1').replace(',', '.'))
        except (InvalidOperation, TypeError):
            coeff = Decimal('1')
        n = 0
        for t in targets:
            _, created = ClassSubject.objects.get_or_create(
                school_class=t, subject=subject,
                defaults={'coefficient': coeff, 'max_grade': Decimal('20'), 'duration_hours': Decimal('2')},
            )
            if created:
                n += 1
        msg = f'{subject.name} ajoutée à {n} classe(s).'
    else:
        return _toast(HttpResponse(status=400), 'Action inconnue.', 'error')

    return _toast(HttpResponse(status=204), msg)


@login_required
@director_or_staff_required
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


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCES — Catalogue de frais & gabarits de tranches (Lot 2)
# ═══════════════════════════════════════════════════════════════════════════════
# Toutes ces vues suivent le pattern settings existant : HTMX + partials + toast via
# header HX-Trigger. Cible principale : #fee-catalog (catalogue) et
# #schedule-templates (gabarits). Aucune n'opère hors de l'école courante.

def _fee_types_qs(school):
    """
    Catalogue de gestion de l'école : tous les frais ACTIFS ET INACTIFS (le template
    sépare les deux), SAUF la scolarité (TUITION) qui est présentée en bannière d'info,
    jamais en carte. Variantes (toutes, actives + inactives) préchargées → zéro N+1 ;
    le template grise les variantes désactivées.
    """
    return (
        FeeType.objects
        .filter(school=school)
        .exclude(category=FeeCategory.TUITION)
        .prefetch_related(
            models.Prefetch(
                'variants',
                queryset=FeeVariant.objects.order_by('order', 'label'),
            )
        )
        .order_by('order', 'name')
    )


def _catalog_context(school):
    """Sépare le catalogue en frais actifs / inactifs (1 seule requête, split en Python)."""
    fees = list(_fee_types_qs(school))
    return {
        'active_fees':   [f for f in fees if f.is_active],
        'inactive_fees': [f for f in fees if not f.is_active],
        'has_any':       bool(fees),
    }


def _render_catalog(request, school):
    """Rend le partial catalogue (cartes actives + section désactivés + état vide)."""
    return render_to_string(
        'settings/partials/fee_catalog.html',
        _catalog_context(school),
        request=request,
    )


def _render_schedules(request, school):
    """Rend le partial gabarits de tranches."""
    return render_to_string(
        'settings/partials/schedule_templates.html',
        {'schedule_templates': PaymentScheduleTemplate.objects
            .filter(school=school, is_active=True)},
        request=request,
    )


def _toast(resp, message, msg_type='success', **extra):
    """Pose un header HX-Trigger avec un toast (+ événements optionnels)."""
    payload = {'showToast': {'message': message, 'type': msg_type}}
    payload.update(extra)
    resp['HX-Trigger'] = json.dumps(payload)
    return resp


@login_required
@director_or_staff_required
def fees(request):
    """Écran principal : catalogue de frais + gabarit de tranches par défaut."""
    school = get_school(request)
    return render(request, 'settings/fees.html', {
        **_catalog_context(school),
        'schedule_templates': PaymentScheduleTemplate.objects
            .filter(school=school, is_active=True),
        'fee_form':           FeeTypeForm(),
        'active_section':     'fees',
        'school':             school,
    })


@login_required
@director_or_staff_required
def fee_form(request, fee_id=None):
    """Renvoie le corps du modal (création si fee_id absent, édition sinon)."""
    school = get_school(request)
    instance = None
    if fee_id is not None:
        instance = get_object_or_404(FeeType, id=fee_id, school=school)
    return render(request, 'settings/partials/fee_form.html', {
        'form':     FeeTypeForm(instance=instance),
        'fee':      instance,
    })


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fee_save(request, fee_id=None):
    """Crée ou met à jour un FeeType depuis le modal (formulaire complet)."""
    school = get_school(request)
    instance = None
    if fee_id is not None:
        instance = get_object_or_404(FeeType, id=fee_id, school=school)

    form = FeeTypeForm(request.POST, instance=instance)
    if not form.is_valid():
        # Réaffiche le formulaire avec ses erreurs DANS le modal. Status 200 volontaire :
        # HTMX swappe le corps du modal (#fee-modal-body) ; le modal reste ouvert tant
        # que le succès (closeFeeModal) n'est pas déclenché.
        return render(request, 'settings/partials/fee_form.html',
                      {'form': form, 'fee': instance})

    obj = form.save(commit=False)
    obj.school = school
    if instance is None:
        # Ordre d'affichage = à la fin du catalogue.
        obj.order = (
            FeeType.objects.filter(school=school)
            .aggregate(m=models.Max('order'))['m'] or 0
        ) + 1
    try:
        with transaction.atomic():
            obj.full_clean(exclude=['school'])  # rejoue les garde-fous du modèle
            obj.save()
    except (IntegrityError, ValidationError):
        return _toast(HttpResponse(status=422),
                      'Un frais portant ce nom existe déjà.', 'error')

    # Succès : on swappe le catalogue (OOB) et on demande la fermeture du modal.
    catalog = _render_catalog(request, school)
    resp = HttpResponse(
        f'<div id="fee-catalog" hx-swap-oob="true">{catalog}</div>'
    )
    return _toast(
        resp,
        'Frais enregistré.' if instance is None else 'Frais modifié.',
        closeFeeModal={},
    )


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fee_amount_update(request, fee_id):
    """Édition inline du montant d'un frais simple (un seul champ)."""
    school = get_school(request)
    fee = get_object_or_404(FeeType, id=fee_id, school=school)
    raw = (request.POST.get('default_amount') or '').strip()
    try:
        amount = int(raw)
        if amount < 0:
            raise ValueError
    except (TypeError, ValueError):
        return _toast(HttpResponse(status=422), 'Montant invalide.', 'error')

    fee.default_amount = amount
    fee.save(update_fields=['default_amount'])
    return _toast(HttpResponse(status=204), 'Montant mis à jour.')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fee_toggle_active(request, fee_id):
    """
    Bascule Actif/Inactif d'un frais. On ne supprime JAMAIS un frais (il pourra porter
    des paiements) : désactiver le retire des inscriptions tout en le gardant en base
    et réactivable. La réactivation peut échouer si un autre frais ACTIF porte déjà ce
    nom (contrainte conditionnelle) → toast clair plutôt que 500.
    """
    school = get_school(request)
    fee = get_object_or_404(FeeType, id=fee_id, school=school)
    fee.is_active = not fee.is_active
    try:
        with transaction.atomic():
            fee.save(update_fields=['is_active'])
    except IntegrityError:
        return _toast(
            HttpResponse(status=422),
            f'Impossible de réactiver : un frais actif « {fee.name} » existe déjà.',
            'error',
        )
    resp = render(request, 'settings/partials/fee_catalog.html',
                  _catalog_context(school))
    return _toast(
        resp,
        'Frais réactivé.' if fee.is_active else 'Frais désactivé.',
        'success' if fee.is_active else 'info',
    )


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fee_variant_add(request, fee_id):
    """Ajoute une variante à un frais à variantes."""
    school = get_school(request)
    fee = get_object_or_404(FeeType, id=fee_id, school=school, has_variants=True)
    form = FeeVariantForm(request.POST)
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        return _toast(HttpResponse(status=422), first, 'error')
    variant = form.save(commit=False)
    variant.fee_type = fee
    # Pour un frais genré, gender_key est imposé par le label de variante choisi
    # (le template envoie 'M'/'F' en champ caché). Sinon il reste NULL.
    variant.order = (
        fee.variants.aggregate(m=models.Max('order'))['m'] or 0
    ) + 1
    try:
        with transaction.atomic():
            variant.save()
    except IntegrityError:
        # Contrainte uniq_fee_variant_type_label : une variante du même libellé existe
        # déjà pour ce frais → on remonte un toast plutôt qu'une 500.
        return _toast(HttpResponse(status=422),
                      f'Une variante « {variant.label} » existe déjà.', 'error')
    resp = render(request, 'settings/partials/fee_card.html',
                  {'fee': _fee_types_qs(school).get(pk=fee.pk)})
    return _toast(resp, 'Variante ajoutée.')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fee_variant_update(request, variant_id):
    """
    Édition inline d'une variante existante (label + montant), sans suppression/recréation.
    On met à jour UNIQUEMENT label et amount : gender_key est préservé tel quel (ne pas
    le clobber pour les frais genrés). Mettre à jour la même ligne ne peut pas violer la
    contrainte d'unicité (même pk) ; renommer vers un label déjà pris (autre variante
    active) → IntegrityError → toast.
    """
    school = get_school(request)
    variant = get_object_or_404(FeeVariant, id=variant_id, fee_type__school=school)

    label = (request.POST.get('label') or '').strip()
    raw_amount = (request.POST.get('amount') or '').strip()
    if not label:
        return _toast(HttpResponse(status=422), 'Le libellé est obligatoire.', 'error')
    try:
        amount = int(raw_amount)
        if amount < 0:
            raise ValueError
    except (TypeError, ValueError):
        return _toast(HttpResponse(status=422), 'Montant invalide.', 'error')

    variant.label = label
    variant.amount = amount
    try:
        with transaction.atomic():
            variant.save(update_fields=['label', 'amount'])
    except IntegrityError:
        return _toast(HttpResponse(status=422),
                      f'Une variante « {label} » existe déjà.', 'error')

    resp = render(request, 'settings/partials/fee_card.html',
                  {'fee': _fee_types_qs(school).get(pk=variant.fee_type_id)})
    return _toast(resp, 'Variante mise à jour.')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fee_variant_toggle(request, variant_id):
    """Bascule Actif/Inactif d'une variante (même logique que le frais : jamais de suppression dure)."""
    school = get_school(request)
    variant = get_object_or_404(FeeVariant, id=variant_id, fee_type__school=school)
    variant.is_active = not variant.is_active
    try:
        with transaction.atomic():
            variant.save(update_fields=['is_active'])
    except IntegrityError:
        return _toast(
            HttpResponse(status=422),
            f'Impossible de réactiver : une variante « {variant.label} » existe déjà.',
            'error',
        )
    resp = render(request, 'settings/partials/fee_card.html',
                  {'fee': _fee_types_qs(school).get(pk=variant.fee_type_id)})
    return _toast(
        resp,
        'Variante réactivée.' if variant.is_active else 'Variante désactivée.',
        'success' if variant.is_active else 'info',
    )


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def schedule_set_default(request, template_id):
    """Passe un gabarit de tranches en « par défaut » (les autres repassent à False)."""
    school = get_school(request)
    tpl = get_object_or_404(PaymentScheduleTemplate, id=template_id, school=school)
    tpl.is_default = True
    tpl.save()  # save() retire le flag des autres gabarits de l'école (cf. modèle)
    resp = render(request, 'settings/partials/schedule_templates.html', {
        'schedule_templates': PaymentScheduleTemplate.objects
            .filter(school=school, is_active=True),
    })
    return _toast(resp, f'Gabarit « {tpl.name} » appliqué par défaut.')


@login_required
@director_or_staff_required
@require_http_methods(['POST'])
def fees_seed(request):
    """
    Pré-remplit un catalogue type malien pour TESTER (déclenchable à la main).

    Volontairement une vue POST et non une data migration : on ne veut pas polluer
    les écoles réelles. Idempotent : get_or_create par nom, ne duplique rien.
    """
    school = get_school(request)
    from apps.finance.seeds import seed_fee_catalog
    seed_fee_catalog(school)
    catalog = _render_catalog(request, school)
    schedules = _render_schedules(request, school)
    resp = HttpResponse(
        f'<div id="fee-catalog" hx-swap-oob="true">{catalog}</div>'
        f'<div id="schedule-templates" hx-swap-oob="true">{schedules}</div>'
    )
    return _toast(resp, 'Catalogue de démonstration chargé.')
