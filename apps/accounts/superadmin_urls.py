from django.urls import path
from . import superadmin_views

app_name = 'superadmin'

urlpatterns = [
    path('', superadmin_views.dashboard, name='dashboard'),
    path('schools/create/', superadmin_views.school_create, name='school-create'),
    path('schools/<int:school_id>/director/', superadmin_views.director_create, name='director-create'),
]
