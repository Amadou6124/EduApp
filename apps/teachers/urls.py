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

    # ── Suivi difficulté ──────────────────────────────────────
    path('difficulty/', views.difficulty_dashboard, name='difficulty'),
    path('difficulty/<int:class_id>/', views.difficulty_class, name='difficulty-class'),

    # ── Évaluation rapide ─────────────────────────────────────
    path('quick-assessment/save/', views.quick_assessment_save, name='quick-assessment-save'),
]
