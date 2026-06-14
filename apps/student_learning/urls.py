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
    # Stubs — phases suivantes
    path('quiz/<int:lesson_id>/', views.learn_quiz_stub, name='quiz'),
    path('flashcards/', views.learn_flashcards_stub, name='flashcards'),
    path('profile/', views.learn_profile_stub, name='profile'),
]
