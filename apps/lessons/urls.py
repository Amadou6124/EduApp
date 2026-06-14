from django.urls import path

from . import views

app_name = 'lessons'

urlpatterns = [
    path('', views.lesson_list, name='list'),
    path('upload/', views.lesson_upload, name='upload'),
    path('<int:lesson_id>/', views.lesson_detail, name='detail'),
    path('<int:lesson_id>/status/', views.lesson_status, name='status'),
    path('<int:lesson_id>/retry/', views.lesson_retry, name='retry'),
]
