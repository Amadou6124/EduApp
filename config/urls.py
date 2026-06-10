from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('', lambda request: redirect('schools:class-list'), name='home'),
    path('', include('apps.accounts.urls')),
    path('', include('apps.schools.urls')),
    path('students/', include('apps.students.urls')),
    path('payments/', include('apps.payments.urls')),
    path('settings/', include('apps.schools.settings_urls')),
    path('superadmin/', include('apps.accounts.superadmin_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
