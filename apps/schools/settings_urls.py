from django.urls import path
from django.views.generic import RedirectView

from . import settings_views

app_name = 'settings'

urlpatterns = [
    # Redirection par défaut → Général
    path('', RedirectView.as_view(pattern_name='settings:general', permanent=False), name='settings-home'),

    # ── ÉCOLE ─────────────────────────────────────────────────────────
    path('general/',      settings_views.general,     name='general'),
    path('appearance/',   settings_views.appearance,  name='appearance'),
    path('school-years/', settings_views.coming_soon, {'section': 'school-years'}, name='school-years'),

    # ── FINANCES ──────────────────────────────────────────────────────
    path('receipt/',         settings_views.receipt,      name='receipt'),
    path('payment-methods/', settings_views.coming_soon,  {'section': 'payment-methods'}, name='payment-methods'),

    # ── DOCUMENTS ─────────────────────────────────────────────────────
    path('bulletin/', settings_views.coming_soon, {'section': 'bulletin'}, name='bulletin'),
    path('headers/',  settings_views.coming_soon, {'section': 'headers'},  name='headers'),

    # ── COMMUNICATION ─────────────────────────────────────────────────
    path('sms/',       settings_views.coming_soon, {'section': 'sms'},       name='sms'),
    path('whatsapp/',  settings_views.coming_soon, {'section': 'whatsapp'},  name='whatsapp'),

    # ── COMPTE ────────────────────────────────────────────────────────
    path('profile/',  settings_views.coming_soon, {'section': 'profile'},  name='profile'),
    path('security/', settings_views.coming_soon, {'section': 'security'}, name='security'),
    path('plan/',     settings_views.coming_soon, {'section': 'plan'},     name='plan'),
]
