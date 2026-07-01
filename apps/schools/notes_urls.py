"""
URLs module notes — /notes/
Namespace : notes
"""
from django.urls import path

from . import notes_views

app_name = 'notes'

urlpatterns = [
    # ── Tableau de bord ───────────────────────────────────────────
    path('', notes_views.notes_dashboard, name='dashboard'),

    # ── Saisie par classe/période ──────────────────────────────────
    path('<int:class_id>/<int:period_id>/',
         notes_views.notes_class,
         name='class'),

    # ── Partial HTMX : changer de matière ─────────────────────────
    path('<int:class_id>/<int:period_id>/<int:subject_id>/',
         notes_views.notes_subject_table,
         name='subject-table'),

    # ── HTMX : sauvegarder une note (upsert) ──────────────────────
    path('note/save/',
         notes_views.note_save,
         name='note-save'),

    # ── HTMX : annuler une note (directeur) ───────────────────────
    path('note/<int:note_id>/cancel/',
         notes_views.note_cancel,
         name='note-cancel'),

    # ── Ouvrir/fermer la saisie d'une période (directeur/staff) ───
    path('period/<int:period_id>/toggle/',
         notes_views.notes_period_toggle,
         name='period-toggle'),
]
