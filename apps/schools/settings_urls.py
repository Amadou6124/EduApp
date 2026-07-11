from django.urls import path
from django.views.generic import RedirectView

from . import settings_views

app_name = 'settings'

urlpatterns = [
    # Index paramètres (drill-in mobile ; desktop = repère)
    path('', settings_views.settings_home, name='settings-home'),

    # ── ÉCOLE ─────────────────────────────────────────────────────────
    path('general/',    settings_views.general,    name='general'),

    # Années scolaires
    path('school-years/',                         settings_views.school_years,        name='school-years'),
    path('school-years/create/',                  settings_views.school_year_create,  name='school-year-create'),
    path('school-years/<int:year_id>/update/',    settings_views.school_year_update,  name='school-year-update'),
    path('school-years/<int:year_id>/delete/',    settings_views.school_year_delete,  name='school-year-delete'),
    path('school-years/<int:year_id>/toggle/',    settings_views.school_year_toggle,  name='school-year-toggle'),
    path('school-years/<int:year_id>/periods/',   settings_views.school_year_periods, name='school-year-periods'),
    path('school-years/<int:year_id>/periods/generate/', settings_views.period_generate, name='period-generate'),
    path('school-years/<int:year_id>/periods/add/',      settings_views.period_create,   name='period-create'),
    path('school-years/<int:year_id>/class/<int:class_id>/reset-periods/', settings_views.period_class_reset, name='period-class-reset'),

    # Périodes
    path('periods/<int:period_id>/update/',       settings_views.period_update,       name='period-update'),
    path('periods/<int:period_id>/toggle-notes/', settings_views.period_toggle_notes, name='period-toggle-notes'),
    path('periods/<int:period_id>/delete/',       settings_views.period_delete,       name='period-delete'),

    # Matières
    path('subjects/',                       settings_views.subjects,       name='subjects'),
    path('subjects/create/',                settings_views.subject_create, name='subject-create'),
    path('subjects/<int:subject_id>/update/', settings_views.subject_update, name='subject-update'),
    path('subjects/<int:subject_id>/delete/', settings_views.subject_delete, name='subject-delete'),

    # Matières par classe
    path('class-subjects/search/',                  settings_views.class_subjects_search, name='class-subjects-search'),
    path('classes/<int:class_id>/subjects/',        settings_views.class_subjects_panel, name='class-subjects'),
    path('classes/<int:class_id>/subjects/add/',    settings_views.class_subject_add,    name='class-subject-add'),
    path('classes/<int:class_id>/subjects/apply-catalog/', settings_views.class_subject_apply_catalog, name='class-subject-apply-catalog'),
    path('classes/<int:class_id>/subjects/copy/',   settings_views.class_subject_copy,   name='class-subject-copy'),
    path('class-subjects/bulk/',                    settings_views.class_subject_bulk,   name='class-subject-bulk'),
    path('class-subjects/<int:cs_id>/update/',      settings_views.class_subject_update, name='class-subject-update'),
    path('class-subjects/<int:cs_id>/remove/',      settings_views.class_subject_remove, name='class-subject-remove'),

    # ── FINANCES ──────────────────────────────────────────────────────
    path('receipt/',         settings_views.receipt,     name='receipt'),
    path('payment-methods/', settings_views.coming_soon, {'section': 'payment-methods'}, name='payment-methods'),

    # Catalogue de frais & gabarits de tranches (Lot 2)
    path('frais/',                        settings_views.fees,              name='fees'),
    path('frais/form/',                   settings_views.fee_form,          name='fee-form'),
    path('frais/save/',                   settings_views.fee_save,          name='fee-create'),
    path('frais/<int:fee_id>/form/',      settings_views.fee_form,          name='fee-edit-form'),
    path('frais/<int:fee_id>/save/',      settings_views.fee_save,          name='fee-update'),
    path('frais/<int:fee_id>/amount/',    settings_views.fee_amount_update, name='fee-amount'),
    path('frais/<int:fee_id>/toggle/',    settings_views.fee_toggle_active, name='fee-toggle'),
    path('frais/<int:fee_id>/variants/add/',          settings_views.fee_variant_add,    name='fee-variant-add'),
    path('frais/variants/<int:variant_id>/update/',   settings_views.fee_variant_update, name='fee-variant-update'),
    path('frais/variants/<int:variant_id>/toggle/',   settings_views.fee_variant_toggle, name='fee-variant-toggle'),
    path('frais/schedule/form/',                      settings_views.schedule_form,        name='schedule-form'),
    path('frais/schedule/save/',                      settings_views.schedule_save,        name='schedule-create'),
    path('frais/schedule/<int:template_id>/form/',    settings_views.schedule_form,        name='schedule-edit-form'),
    path('frais/schedule/<int:template_id>/save/',    settings_views.schedule_save,        name='schedule-update'),
    path('frais/schedule/<int:template_id>/toggle/',  settings_views.schedule_toggle_active, name='schedule-toggle'),
    path('frais/schedule/<int:template_id>/default/', settings_views.schedule_set_default, name='schedule-set-default'),

    # ── DOCUMENTS ─────────────────────────────────────────────────────
    path('bulletin/', settings_views.bulletin, name='bulletin'),
    path('bulletin/appreciations/add/',                   settings_views.appreciation_add,    name='appreciation-add'),
    path('bulletin/appreciations/seed/',                  settings_views.appreciation_seed,   name='appreciation-seed'),
    path('bulletin/appreciations/<int:scale_id>/save/',   settings_views.appreciation_update, name='appreciation-update'),
    path('bulletin/appreciations/<int:scale_id>/delete/', settings_views.appreciation_delete, name='appreciation-delete'),
    path('headers/',  settings_views.coming_soon, {'section': 'headers'},  name='headers'),

    # ── COMMUNICATION ─────────────────────────────────────────────────
    path('sms/',      settings_views.coming_soon, {'section': 'sms'},      name='sms'),
    path('whatsapp/', settings_views.coming_soon, {'section': 'whatsapp'}, name='whatsapp'),

    # ── COMPTE ────────────────────────────────────────────────────────
    path('profile/',  settings_views.coming_soon, {'section': 'profile'},  name='profile'),
    path('security/', settings_views.coming_soon, {'section': 'security'}, name='security'),
    path('plan/',     settings_views.coming_soon, {'section': 'plan'},     name='plan'),
]
