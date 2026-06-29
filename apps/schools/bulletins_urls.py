"""
URLs module bulletins — /bulletins/
Namespace : bulletins
"""
from django.urls import path

from . import bulletins_views

app_name = 'bulletins'

urlpatterns = [
    # ── Page principale (3 onglets) ─────────────────────────────
    path('', bulletins_views.bulletins_main, name='main'),

    # ── HTMX partials : onglets ──────────────────────────────────
    path('health/',
         bulletins_views.health_tab,
         name='health-tab'),
    path('list/',
         bulletins_views.bulletins_tab,
         name='bullets-tab'),
    path('rankings/',
         bulletins_views.rankings_tab,
         name='rankings-tab'),

    # ── Génération ──────────────────────────────────────────────
    path('generate/class/<int:class_id>/<int:period_id>/',
         bulletins_views.generate_class_bulletins,
         name='generate-class'),
    path('generate/student/<int:student_id>/<int:period_id>/',
         bulletins_views.generate_student_bulletin,
         name='generate-student'),

    # ── Génération / publication groupées (vue école) ───────────
    path('generate-all/<int:period_id>/',
         bulletins_views.generate_all_classes,
         name='generate-all'),
    path('publish-all/<int:period_id>/',
         bulletins_views.publish_all_classes,
         name='publish-all'),

    # ── Actions ──────────────────────────────────────────────────
    path('preview/<int:bulletin_id>/',
         bulletins_views.bulletin_preview,
         name='preview'),
    path('download/<int:bulletin_id>/',
         bulletins_views.bulletin_download,
         name='download'),
    path('publish/<int:bulletin_id>/',
         bulletins_views.bulletin_publish,
         name='publish'),
    path('view-pdf/<int:bulletin_id>/',
         bulletins_views.bulletin_view_pdf,
         name='view-pdf'),
    path('download-all/<int:class_id>/<int:period_id>/',
         bulletins_views.bulletin_download_all,
         name='download-all'),
    path('rankings-export/<int:class_id>/<int:period_id>/',
         bulletins_views.rankings_export,
         name='rankings-export'),
]