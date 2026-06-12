import mimetypes
import os

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect


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
    path('', lambda request: redirect('schools:class-list'), name='home'),
    path('', include('apps.accounts.urls')),
    path('', include('apps.schools.urls')),
    path('students/', include('apps.students.urls')),
    path('payments/', include('apps.payments.urls')),
    path('notes/',      include('apps.schools.notes_urls')),
    path('dashboard/',  include('apps.dashboard.urls')),
    path('bulletins/',  include('apps.schools.bulletins_urls')),
    path('settings/', include('apps.schools.settings_urls')),
    path('superadmin/', include('apps.accounts.superadmin_urls')),
    path('media/<path:path>', protected_media, name='protected-media'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
