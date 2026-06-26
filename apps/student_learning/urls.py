from django.urls import path

from . import views

app_name = 'learn'

urlpatterns = [
    path('login/', views.learn_login, name='login'),
    path('logout/', views.learn_logout, name='logout'),
    path('', views.learn_dashboard, name='dashboard'),
    # Lecture leçon (Phase 5)
    path('lesson/<int:lesson_id>/', views.learn_lesson, name='lesson'),
    path('lesson/<int:lesson_id>/progress/', views.lesson_save_progress, name='lesson-progress'),
    path('lesson/<int:lesson_id>/note/', views.lesson_save_note, name='lesson-note'),
    path('lesson/<int:lesson_id>/complete/', views.lesson_complete, name='lesson-complete'),
    # Stories interactives (Phase 10)
    path('lesson/<int:lesson_id>/story/', views.learn_story, name='story'),
    path('lesson/<int:lesson_id>/story/answer/', views.story_answer, name='story-answer'),
    path('lesson/<int:lesson_id>/story/finish/', views.story_finish, name='story-finish'),
    # Quiz engine (Phase 6)
    path('quiz/<int:lesson_id>/', views.learn_quiz, name='quiz'),
    path('quiz/<int:lesson_id>/submit/', views.quiz_submit, name='quiz-submit'),
    path('quiz/<int:lesson_id>/results/', views.quiz_results, name='quiz-results'),
    # Stubs — phases suivantes
    # Flashcards SM-2 (Phase 8)
    path('flashcards/', views.learn_flashcards, name='flashcards'),
    path('flashcards/<int:lesson_id>/', views.flashcards_session, name='flashcards-session'),
    path('flashcards/review/<int:card_id>/', views.flashcard_review, name='flashcard-review'),
    # Notes & Rangs (Phase 11)
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
