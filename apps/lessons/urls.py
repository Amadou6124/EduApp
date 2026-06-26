from django.urls import path

from . import views

app_name = 'lessons'

urlpatterns = [
    path('', views.lesson_list, name='list'),
    path('upload/', views.lesson_upload, name='upload'),
    path('<int:lesson_id>/', views.lesson_detail, name='detail'),
    path('<int:lesson_id>/status/',  views.lesson_status,  name='status'),
    path('<int:lesson_id>/retry/',   views.lesson_retry,   name='retry'),
    path('<int:lesson_id>/preview/', views.lesson_preview, name='preview'),
    path('<int:lesson_id>/deploy/<int:class_id>/', views.lesson_deploy_toggle, name='deploy-toggle'),

    # v2 — upload d'unité (parallèle au v1)
    path('unit/',                        views.unit_list,     name='unit-list'),
    path('unit/upload/',                 views.unit_upload,   name='unit-upload'),
    path('unit/<int:unit_id>/',          views.unit_detail,   name='unit-detail'),
    path('unit/<int:unit_id>/generate/', views.unit_generate, name='unit-generate'),
    path('unit/<int:unit_id>/status/',   views.unit_status,   name='unit-status'),
]
