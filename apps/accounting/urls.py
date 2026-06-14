from django.urls import path

from . import views

app_name = 'accounting'

urlpatterns = [
    # ── Phase 2 — Liste & rémunération ───────────────────────────
    path('staff/', views.accounting_staff_list, name='staff-list'),
    path('staff/<int:user_id>/remuneration/',
         views.employee_remuneration_panel, name='staff-remuneration'),
    path('staff/<int:user_id>/remuneration/save/',
         views.employee_remuneration_save, name='staff-remuneration-save'),

    # ── Phase 3 — Émargement ─────────────────────────────────────
    path('emargement/', views.emargement_dashboard, name='emargement'),
    path('emargement/save/', views.emargement_save, name='emargement-save'),
    path('emargement/substitute/', views.emargement_substitute_search, name='emargement-substitute'),
]
