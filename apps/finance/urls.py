from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    # Encaissement au guichet (lot 5) — depuis la fiche élève.
    path('collect/<int:student_id>/panel/',   views.collect_panel,   name='collect-panel'),
    path('collect/<int:student_id>/preview/',  views.collect_preview, name='collect-preview'),
    path('collect/<int:student_id>/create/',   views.collect_create,  name='collect-create'),
]
