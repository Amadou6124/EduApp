from django.urls import path

from . import views

app_name = 'promoter'

urlpatterns = [
    path('', views.promoter_dashboard, name='dashboard'),
]
