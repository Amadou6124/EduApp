from django.urls import path

from . import views

app_name = 'learn'

urlpatterns = [
    path('login/', views.learn_login, name='login'),
    path('logout/', views.learn_logout, name='logout'),
    path('', views.learn_dashboard, name='dashboard'),
    # Stubs — phases suivantes
    path('lesson/<int:lesson_id>/', views.learn_lesson_stub, name='lesson'),
    path('quiz/<int:lesson_id>/', views.learn_quiz_stub, name='quiz'),
    path('flashcards/', views.learn_flashcards_stub, name='flashcards'),
    path('profile/', views.learn_profile_stub, name='profile'),
]
