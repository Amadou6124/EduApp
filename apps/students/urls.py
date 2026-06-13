from django.urls import path

from . import views

app_name = 'students'

urlpatterns = [
    path('',                        views.student_list,             name='list'),
    path('create/',                 views.student_create,           name='create'),
    path('create/group/',           views.student_create_group,     name='create-group'),
    path('search/',                 views.student_search,           name='search'),
    path('import/template/',        views.student_import_template,  name='import-template'),
    path('import/preview/',         views.student_import_preview,   name='import-preview'),
    path('import/confirm/',         views.student_import_confirm,   name='import-confirm'),
    path('<int:student_id>/',        views.student_detail,           name='detail'),
    path('<int:student_id>/edit/',                          views.student_update,        name='update'),
    path('<int:student_id>/observations/<int:obs_id>/read/', views.observation_mark_read, name='obs-mark-read'),
    path('<int:student_id>/guardians/search/',                   views.guardian_search, name='guardian-search'),
    path('<int:student_id>/guardians/add/',                      views.guardian_add,    name='guardian-add'),
    path('<int:student_id>/guardians/<int:guardian_id>/remove/', views.guardian_remove, name='guardian-remove'),
]
