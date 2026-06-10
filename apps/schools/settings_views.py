import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .forms import (
    AppearanceForm, GeneralSettingsForm,
    ReceiptModeForm, ReceiptUploadForm,
)
from .models import School
from .views import get_demo_school as _get_school

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


def _custom_step(school):
    """Détermine l'étape courante du flux de reçu personnalisé."""
    if school.receipt_configured_at:
        return 'configured'
    if school.receipt_template_pdf:
        return 'uploaded'
    return 'empty'


@login_required(login_url='/admin/login/')
def general(request):
    school = _get_school()
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


@login_required(login_url='/admin/login/')
def appearance(request):
    school = _get_school()
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


@login_required(login_url='/admin/login/')
def receipt(request):
    school = _get_school()
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'set_mode':
            mode = request.POST.get('receipt_mode', 'standard')
            if mode in ('standard', 'custom'):
                school.receipt_mode = mode
                school.save(update_fields=['receipt_mode'])
            school.refresh_from_db()
            resp = render(request, 'settings/partials/receipt_content.html', {
                'school': school, 'custom_step': _custom_step(school),
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Mode mis à jour.', 'type': 'success'}}
            )
            return resp

        elif action == 'upload_pdf':
            form = ReceiptUploadForm(request.POST, request.FILES, instance=school)
            if form.is_valid():
                form.save()
                school.refresh_from_db()
                return render(request, 'settings/partials/receipt_content.html', {
                    'school': school, 'custom_step': _custom_step(school),
                })
            return render(request, 'settings/partials/receipt_content.html', {
                'school': school, 'custom_step': 'empty',
                'upload_error': form.errors.get('receipt_template_pdf', ['Erreur inconnue.'])[0],
            })

        elif action == 'analyze':
            mock_mapping = [
                {'zone': 'Nom de l\'élève', 'variable': 'nom_eleve',      'confidence': 'high'},
                {'zone': 'Classe :',         'variable': 'classe',          'confidence': 'high'},
                {'zone': 'Montant versé :',  'variable': 'montant',         'confidence': 'high'},
                {'zone': 'Date :',           'variable': 'date',            'confidence': 'high'},
                {'zone': 'N° Reçu :',        'variable': 'numero_recu',     'confidence': 'medium'},
                {'zone': 'Solde restant :',  'variable': 'solde',           'confidence': 'medium'},
                {'zone': 'Mode règlement :', 'variable': 'mode_paiement',   'confidence': 'low'},
            ]
            return render(request, 'settings/partials/receipt_content.html', {
                'school': school, 'custom_step': 'mapping',
                'mapping': mock_mapping, 'variables': _RECEIPT_VARIABLES,
            })

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
            resp = render(request, 'settings/partials/receipt_content.html', {
                'school': school, 'custom_step': _custom_step(school),
            })
            resp['HX-Trigger'] = json.dumps(
                {'showToast': {'message': 'Modèle de reçu configuré avec succès.', 'type': 'success'}}
            )
            return resp

    return render(request, 'settings/receipt.html', {
        'school': school,
        'active_section': 'receipt',
        'custom_step': _custom_step(school),
    })


@login_required(login_url='/admin/login/')
def coming_soon(request, section):
    title, description, icon = _COMING_SOON_META.get(
        section, ('Section', 'Cette section sera disponible prochainement.', 'document'),
    )
    return render(request, 'settings/coming_soon.html', {
        'active_section': section,
        'section_title':  title,
        'section_desc':   description,
        'section_icon':   icon,
    })
