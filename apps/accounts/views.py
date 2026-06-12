from django.contrib.auth import login, logout
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .forms import LoginForm
from .models import UserRole

_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 15 * 60  # 15 minutes


# ── Helpers rate limiting ──────────────────────────────────────────────────

def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', 'unknown')


def _is_locked(key):
    return bool(cache.get(f'login_lock_{key}'))


def _record_failure(key):
    fail_key = f'login_fail_{key}'
    attempts = (cache.get(fail_key) or 0) + 1
    cache.set(fail_key, attempts, _LOCKOUT_SECS)
    if attempts >= _MAX_ATTEMPTS:
        cache.set(f'login_lock_{key}', True, _LOCKOUT_SECS)


def _clear_failures(key):
    cache.delete(f'login_fail_{key}')
    cache.delete(f'login_lock_{key}')


# ── Redirect post-login selon rôle ────────────────────────────────────────

def _post_login_url(request, user):
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    if user.is_superuser:
        return '/superadmin/'
    if user.role in (UserRole.DIRECTOR, UserRole.STAFF):
        return '/dashboard/'
    if user.role == UserRole.TEACHER:
        return '/notes/'
    if user.role == UserRole.STUDENT:
        return '/portal/student/'
    if user.role == UserRole.PARENT:
        return '/portal/parent/'
    return '/classes/'


# ── Vues ──────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect(_post_login_url(request, request.user))

    ip    = _client_ip(request)
    phone = request.POST.get('username', '').strip()

    # Verrou par IP ou par numéro de compte (résistant au spoofing X-Forwarded-For)
    locked = _is_locked(f'ip_{ip}') or (phone and _is_locked(f'phone_{phone}'))

    if request.method == 'POST' and not locked:
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            _clear_failures(f'ip_{ip}')
            _clear_failures(f'phone_{phone}')
            login(request, user, backend='apps.accounts.backends.PhoneBackend')
            return redirect(_post_login_url(request, user))
        _record_failure(f'ip_{ip}')
        if phone:
            _record_failure(f'phone_{phone}')
        locked = _is_locked(f'ip_{ip}') or (phone and _is_locked(f'phone_{phone}'))
    else:
        form = LoginForm(request)

    return render(request, 'accounts/login.html', {
        'form':   form,
        'locked': locked,
        'next':   request.GET.get('next', ''),
    })


@require_http_methods(['GET', 'POST'])
def logout_view(request):
    logout(request)
    messages.success(request, 'Vous avez été déconnecté avec succès.')
    return redirect('accounts:login')


@login_required
def portal_coming_soon(request):
    role_labels = {
        UserRole.STUDENT: ('Portail Élève', 'student'),
        UserRole.PARENT:  ('Portail Parent', 'parent'),
    }
    role_label, role_key = role_labels.get(
        getattr(request.user, 'role', None),
        ('Portail', 'default')
    )
    return render(request, 'accounts/portal_coming_soon.html', {
        'role_label': role_label,
        'role_key':   role_key,
    })
