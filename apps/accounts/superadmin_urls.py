from django.urls import path
from . import superadmin_views

app_name = 'superadmin'

urlpatterns = [
    path('', superadmin_views.dashboard, name='dashboard'),
    path('schools/create/', superadmin_views.school_create, name='school-create'),
    path('schools/<int:school_id>/edit/', superadmin_views.school_update, name='school-update'),
    path('schools/<int:school_id>/director/', superadmin_views.director_create, name='director-create'),
    path('schools/<int:school_id>/director/<int:director_id>/edit/', superadmin_views.director_update, name='director-update'),
]
