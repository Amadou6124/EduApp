from django.urls import path

from . import views

app_name = 'parent'

urlpatterns = [
    path('', views.parent_dashboard, name='dashboard'),
    path('bulletin/<int:bulletin_id>/pdf/', views.parent_bulletin_pdf, name='bulletin-pdf'),
]
