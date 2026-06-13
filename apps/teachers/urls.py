"""
URLs Portail Professeur — /teacher/
Namespace : teacher
"""
from django.urls import path

from . import views

app_name = 'teacher'

urlpatterns = [
    # ── Dashboard professeur ──────────────────────────────────
    path('', views.teacher_dashboard, name='dashboard'),

    # ── Absences ──────────────────────────────────────────────
    path('absences/', views.attendance_list, name='attendance-list'),
    path('absences/<int:class_id>/', views.attendance_class, name='attendance-class'),
    path('absences/<int:class_id>/save/', views.attendance_save, name='attendance-save'),

    # ── Élèves (lecture seule) ────────────────────────────────
    path('students/', views.teacher_students, name='students'),
    path('students/<int:student_id>/', views.teacher_student_detail, name='student-detail'),
    path('students/<int:student_id>/observe/', views.observation_create, name='observe'),
]
