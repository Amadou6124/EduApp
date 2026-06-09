from django.urls import path
from . import views

app_name = 'schools'

urlpatterns = [
    path('classes/', views.class_list, name='class-list'),
    path('classes/create/', views.class_create, name='class-create'),
    path('classes/search/', views.class_search, name='class-search'),
    path('classes/<int:class_id>/edit/', views.class_edit_form, name='class-edit-form'),
    path('classes/<int:class_id>/update/', views.class_update, name='class-update'),
    path('classes/<int:class_id>/delete/', views.class_delete, name='class-delete'),
    path('classes/<int:class_id>/row/', views.class_row, name='class-row'),
    path('classes/<int:class_id>/edit-modal/', views.class_edit_modal, name='class-edit-modal'),
]
