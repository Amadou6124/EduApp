from django.urls import path
from . import views

app_name = 'schools'

urlpatterns = [
    path('classes/', views.class_list, name='class-list'),
    path('announcements/',                  views.announcement_list,    name='announcement-list'),
    path('announcements/form/',             views.announcement_form,    name='announcement-form'),
    path('announcements/create/',           views.announcement_create,  name='announcement-create'),
    path('announcements/<int:pk>/update/',  views.announcement_update,  name='announcement-update'),
    path('announcements/<int:pk>/publish/', views.announcement_publish, name='announcement-publish'),
    path('announcements/<int:pk>/delete/',  views.announcement_delete,  name='announcement-delete'),
    path('classes/create/', views.class_create, name='class-create'),
    path('classes/search/', views.class_search, name='class-search'),
    path('classes/import/template/', views.class_import_template, name='class-import-template'),
    path('classes/import/preview/', views.class_import_preview, name='class-import-preview'),
    path('classes/import/confirm/', views.class_import_confirm, name='class-import-confirm'),
    path('classes/<int:class_id>/edit/', views.class_edit_form, name='class-edit-form'),
    path('classes/<int:class_id>/update/', views.class_update, name='class-update'),
    path('classes/<int:class_id>/delete/', views.class_delete, name='class-delete'),
    path('classes/<int:class_id>/row/', views.class_row, name='class-row'),
    path('classes/<int:class_id>/edit-modal/', views.class_edit_modal, name='class-edit-modal'),
    # Emploi du temps (créneaux + pauses) — grille dans la fiche classe
    path('classes/<int:class_id>/edt/slot/save/',                 views.slot_save,    name='slot-create'),
    path('classes/<int:class_id>/edt/slot/<int:slot_id>/save/',   views.slot_save,    name='slot-update'),
    path('classes/<int:class_id>/edt/slot/<int:slot_id>/delete/', views.slot_delete,  name='slot-delete'),
    path('classes/<int:class_id>/edt/break/save/',                views.break_save,   name='break-create'),
    path('classes/<int:class_id>/edt/break/<int:break_id>/delete/', views.break_delete, name='break-delete'),
    path('classes/<int:class_id>/edt/imprimer/',                  views.class_timetable_print,   name='class-edt-print'),
    path('edt/prof/<int:user_id>/',                               views.teacher_timetable_print, name='teacher-edt'),
    path('classes/<int:class_id>/', views.class_detail, name='class-detail'),
]
