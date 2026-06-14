import mimetypes
import os

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect


def _home_redirect(request):
    """Redirige vers la page d'accueil selon le rôle de l'utilisateur."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    from apps.accounts.views import _post_login_url
    return redirect(_post_login_url(request, request.user))


@login_required
def protected_media(request, path):
    """Sert les fichiers media uniquement aux utilisateurs authentifiés."""
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise Http404
    # Empêche la traversée de répertoire
    real_path = os.path.realpath(file_path)
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    if not real_path.startswith(media_root + os.sep):
        raise Http404
    content_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(open(file_path, 'rb'), content_type=content_type or 'application/octet-stream')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('', _home_redirect, name='home'),
    path('', include('apps.accounts.urls')),
    path('', include('apps.schools.urls')),
    path('students/', include('apps.students.urls')),
    path('payments/', include('apps.payments.urls')),
    path('notes/',      include('apps.schools.notes_urls')),
    path('dashboard/',  include('apps.dashboard.urls')),
    path('bulletins/',  include('apps.schools.bulletins_urls')),
    path('settings/', include('apps.schools.settings_urls')),
    path('team/',       include('apps.accounts.team_urls')),
    path('superadmin/', include('apps.accounts.superadmin_urls')),
    path('teacher/',    include('apps.teachers.urls')),
    path('promoter/',   include('apps.promoter.urls')),
    path('portal/parent/', include('apps.parent.urls')),
    path('media/<path:path>', protected_media, name='protected-media'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
