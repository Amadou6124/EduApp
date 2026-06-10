from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect

from .models import School
from .views import get_demo_school as _get_school

# Métadonnées des sections "coming soon"
_COMING_SOON_META = {
    'school-years': (
        'Années scolaires',
        'Gérez les années scolaires, archivez une année et initialisez la suivante.',
        'calendar',
    ),
    'payment-methods': (
        'Modes de paiement',
        'Configurez les modes de paiement acceptés par votre établissement.',
        'credit-card',
    ),
    'bulletin': (
        'Modèle de bulletin',
        'Personnalisez la mise en page des bulletins de notes PDF.',
        'document',
    ),
    'headers': (
        'En-têtes officiels',
        'Définissez l\'en-tête officiel de l\'établissement pour les documents administratifs.',
        'template',
    ),
    'sms': (
        'Notifications SMS',
        'Envoyez des alertes automatiques aux parents par SMS.',
        'chat',
    ),
    'whatsapp': (
        'Notifications WhatsApp',
        'Communiquez avec les parents via WhatsApp Business.',
        'phone',
    ),
    'profile': (
        'Mon profil',
        'Modifiez vos informations personnelles et votre mot de passe.',
        'user',
    ),
    'security': (
        'Sécurité',
        'Gérez les accès, les sessions actives et l\'authentification à deux facteurs.',
        'lock',
    ),
    'plan': (
        'Plan et usage',
        'Consultez votre forfait actuel, l\'usage et les options de mise à niveau.',
        'chart',
    ),
}


@login_required(login_url='/admin/login/')
def general(request):
    """Section Général — informations de base de l'école."""
    school = _get_school()
    return render(request, 'settings/general.html', {
        'school':         school,
        'active_section': 'general',
    })


@login_required(login_url='/admin/login/')
def appearance(request):
    """Section Apparence — logo et couleur principale."""
    school = _get_school()
    return render(request, 'settings/appearance.html', {
        'school':         school,
        'active_section': 'appearance',
    })


@login_required(login_url='/admin/login/')
def receipt(request):
    """Section Modèle de reçu — standard EduApp ou PDF personnalisé."""
    school = _get_school()
    return render(request, 'settings/receipt.html', {
        'school':         school,
        'active_section': 'receipt',
    })


@login_required(login_url='/admin/login/')
def coming_soon(request, section):
    """Vue générique pour les sections non encore implémentées."""
    title, description, icon = _COMING_SOON_META.get(
        section,
        ('Section', 'Cette section sera disponible prochainement.', 'document'),
    )
    return render(request, 'settings/coming_soon.html', {
        'active_section':  section,
        'section_title':   title,
        'section_desc':    description,
        'section_icon':    icon,
    })
