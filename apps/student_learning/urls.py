from django.urls import path

from . import views

app_name = 'learn'

urlpatterns = [
    path('login/', views.learn_login, name='login'),
    path('logout/', views.learn_logout, name='logout'),
    path('', views.learn_dashboard, name='dashboard'),
    # (v1 retiré : lesson reader, story v1, quiz v1, flashcards — remplacés par le portail v2)
    # (affichage clair Notes/Profil retiré ; plomberie données préservée dans views.py
    #  — student_grades_context / student_stats — pour rebrancher les futures pages dark)
    # PDF bulletin (plomberie conservée, sera re-liée depuis la future page Notes dark)
    path('grades/bulletin/<int:bulletin_id>/pdf/', views.learn_bulletin_pdf, name='bulletin-pdf'),

    # v2 (Phase C) — vues RÉELLES (données de production, élève authentifié).
    path('v2/lesson/<int:lesson_id>/parcours/', views.learn_parcours_v2, name='parcours-v2'),
    path('v2/lesson/<int:lesson_id>/lecteur/',  views.learn_lecteur_v2,  name='lecteur-v2'),
    path('v2/lesson/<int:lesson_id>/concept/<str:concept_id>/quiz/',
         views.learn_quiz_v2, name='quiz-v2'),
    path('v2/lesson/<int:lesson_id>/concept/<str:concept_id>/quiz/answer/',
         views.quiz_v2_answer, name='quiz-v2-answer'),
    path('v2/lesson/<int:lesson_id>/story/',        views.learn_story_v2,  name='story-v2'),
    path('v2/lesson/<int:lesson_id>/story/finish/', views.story_v2_finish, name='story-v2-finish'),
    path('v2/lesson/<int:lesson_id>/exam/',         views.learn_exam_v2,   name='exam-v2'),
    path('v2/lesson/<int:lesson_id>/exam/submit/',  views.exam_v2_submit,  name='exam-v2-submit'),
]
