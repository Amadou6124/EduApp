from django.urls import path

from . import views

app_name = 'promoter'

urlpatterns = [
    path('',                        views.promoter_synthese,      name='synthese'),
    path('ecoles/',                 views.promoter_ecoles,        name='ecoles'),
    path('school/<int:school_id>/', views.promoter_school_detail, name='school-detail'),
    path('finances/',               views.promoter_finances,      name='finances'),
]
