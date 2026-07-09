from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)

if not DEBUG and 'insecure' in SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY non configurée : la valeur par défaut 'django-insecure-*' "
        "ne peut pas être utilisée en production. Définissez SECRET_KEY dans le fichier .env."
    )
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Origines de confiance pour le CSRF (HTTPS) — requis derrière ngrok / un domaine
# de déploiement, sinon les POST (login…) échouent en 403. Piloté par env ;
# supporte les wildcards de sous-domaine (ex. https://*.ngrok-free.app).
CSRF_TRUSTED_ORIGINS = [o for o in config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv()) if o]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # i18n
    'django.contrib.humanize',
    # Librairies tierces
    'django_htmx',
    # Applications EduApp
    'apps.core',
    'apps.accounts',
    'apps.schools',
    'apps.students',
    'apps.payments',
    'apps.dashboard',
    'apps.teachers',
    'apps.promoter',
    'apps.parent',
    'apps.notifications',
    'apps.accounting',
    'apps.finance',
    'apps.lessons',
    'apps.student_learning',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.SchoolMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'apps.core.context_processors.school_context',
                'apps.notifications.context_processors.parent_unread',
                'apps.notifications.context_processors.teacher_unread',
                'apps.parent.context_processors.parent_header',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Base de données PostgreSQL (SQLite en développement si pas de .env)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='eduapp'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# En hébergement managé (Render/Heroku), la base est fournie via une seule variable
# DATABASE_URL. Si elle est présente, elle prime sur les DB_* ci-dessus.
_DATABASE_URL = config('DATABASE_URL', default='')
if _DATABASE_URL:
    import dj_database_url
    DATABASES['default'] = dj_database_url.parse(
        _DATABASE_URL, conn_max_age=600, ssl_require=not DEBUG,
    )

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalisation — Français par défaut
LANGUAGE_CODE = 'fr'
TIME_ZONE = 'Africa/Abidjan'
USE_I18N = True
USE_L10N = True
USE_TZ = True

from django.utils.translation import gettext_lazy as _
LANGUAGES = [
    ('fr', _('Français')),
    ('en', _('Anglais')),
    ('ar', _('Arabe')),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

# Fichiers statiques
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Fichiers media (photos élèves, etc.)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Modèle utilisateur personnalisé
AUTH_USER_MODEL = 'accounts.User'

# Backends d'authentification — PhoneBackend en priorité
AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.PhoneBackend',
    'django.contrib.auth.backends.ModelBackend',  # fallback superadmin Django
]

# URLs auth
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = '/classes/'
LOGOUT_REDIRECT_URL = '/login/'

# Session — expire après 8h d'inactivité
SESSION_COOKIE_AGE = 8 * 60 * 60        # 8 heures en secondes
SESSION_SAVE_EVERY_REQUEST = True        # réinitialise le timer à chaque requête

# ── Cache — table Postgres partagée entre workers ─────────────────────────────
# Indispensable au rate-limiting du login (apps/accounts/views.py) : le cache par
# défaut (LocMemCache) est propre à chaque worker gunicorn — les compteurs d'échecs
# ne seraient pas partagés, ni conservés au redémarrage. DatabaseCache réutilise le
# Postgres existant (zéro infra en plus). La table est créée par `createcachetable`
# (build.sh), et automatiquement par le test runner.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'eduapp_cache',
    }
}

# Sécurité HTTPS — activée uniquement en production
if not DEBUG:
    # Derrière un proxy HTTPS (Render, PythonAnywhere, ngrok…), Django voit du HTTP :
    # ce header lui dit que la requête d'origine est bien en HTTPS, sinon SECURE_SSL_REDIRECT
    # part en boucle de redirection.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE  = True
    CSRF_COOKIE_SECURE     = True
    SECURE_SSL_REDIRECT    = True
    SECURE_HSTS_SECONDS    = 31536000   # 1 an
    SECURE_HSTS_PRELOAD    = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# ── Logging — erreurs visibles dans la console runserver ──────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.template': {
            'handlers': ['console'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# ── Monitoring des erreurs (Sentry) — actif uniquement si SENTRY_DSN est défini ──
# En prod, permet d'être alerté d'un 500 avant que l'utilisateur n'appelle.
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=config('SENTRY_ENV', default='production'),
        traces_sample_rate=0.0,     # pas de tracing perf par défaut (coût) ; à monter au besoin
        send_default_pii=False,     # ne jamais envoyer de données perso par défaut
    )
