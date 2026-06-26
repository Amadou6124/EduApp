from django.urls import path

from . import views

app_name = 'lessons'

urlpatterns = [
    # Déploiement (PARTAGÉ v1/v2 — utilisé par le déploiement v2). À GARDER.
    path('<int:lesson_id>/deploy/<int:class_id>/', views.lesson_deploy_toggle, name='deploy-toggle'),

    # v2 — upload d'unité (le v1 a été retiré : list/upload/detail/status/retry/preview)
    path('unit/',                        views.unit_list,     name='unit-list'),
    path('unit/upload/',                 views.unit_upload,   name='unit-upload'),
    path('unit/<int:unit_id>/',          views.unit_detail,   name='unit-detail'),
    path('unit/<int:unit_id>/generate/', views.unit_generate, name='unit-generate'),
    path('unit/<int:unit_id>/status/',   views.unit_status,   name='unit-status'),
]
