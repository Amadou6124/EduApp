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

    # ── Phase 4 — Paie mensuelle ─────────────────────────────────
    path('salaires/', views.salary_dashboard, name='salaires'),
    path('salaires/pay/', views.salary_pay, name='salary-pay'),
    path('salaires/<int:payment_id>/confirm/', views.salary_confirm, name='salary-confirm'),
    path('salaires/<int:payment_id>/cancel/', views.salary_cancel, name='salary-cancel'),
    path('salaires/<int:payment_id>/pdf/', views.payslip_pdf, name='payslip-pdf'),

    # ── Phase 5 — Dépenses ───────────────────────────────────────
    path('depenses/', views.expense_dashboard, name='depenses'),
    path('depenses/add/', views.expense_create, name='expense-create'),
    path('depenses/<int:expense_id>/cancel/', views.expense_cancel, name='expense-cancel'),

    # ── Phase 6 — Bilan financier ────────────────────────────────
    path('bilan/', views.bilan_dashboard, name='bilan'),
    path('bilan/export/', views.bilan_export_excel, name='bilan-export'),
]
