from django.urls import path

from . import views

app_name = 'learn'

urlpatterns = [
    path('login/', views.learn_login, name='login'),
    path('logout/', views.learn_logout, name='logout'),
    path('', views.learn_dashboard, name='dashboard'),
    # (v1 retiré : lesson reader, story v1, quiz v1, flashcards — remplacés par le portail v2)
    # Notes & Rangs (orthogonal — conservé)
    path('grades/', views.learn_grades, name='grades'),
    path('grades/bulletin/<int:bulletin_id>/pdf/', views.learn_bulletin_pdf, name='bulletin-pdf'),
    path('profile/', views.learn_profile, name='profile'),

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

    # v2 (Phase C) — portail élève redesign. Démos (données en dur).
    path('v2/parcours/', views.parcours_v2_demo, name='parcours-v2-demo'),
    path('v2/lecteur/',  views.lecteur_v2_demo,  name='lecteur-v2-demo'),
    path('v2/quiz-math/',    views.quiz_math_v2_demo,    name='quiz-math-v2-demo'),
    path('v2/quiz-choisir/', views.quiz_choisir_v2_demo, name='quiz-choisir-v2-demo'),
    path('v2/quiz-nombre/',   views.quiz_nombre_v2_demo,   name='quiz-nombre-v2-demo'),
    path('v2/quiz-ordonner/',  views.quiz_ordonner_v2_demo,  name='quiz-ordonner-v2-demo'),
    path('v2/quiz-associer/',  views.quiz_associer_v2_demo,  name='quiz-associer-v2-demo'),
    path('v2/story/',          views.story_v2_demo,          name='story-v2-demo'),
    path('v2/exam/',           views.exam_v2_demo,           name='exam-v2-demo'),
]
