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
]
