"""
Django settings for the Pharmacy Cashback SaaS platform.

See CLAUDE.md §9 for the tech stack and conventions this file implements.
"""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(REPO_ROOT / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Needed when the app is served through a tunnel (ngrok, jprq, etc.) whose
# public HTTPS origin differs from the Host header Django sees — otherwise
# Django's CSRF check rejects browser POSTs (login, seller-web forms).
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# In production, nginx terminates TLS and proxies plain HTTP to this app —
# without this, Django thinks every request is insecure (wrong scheme in
# generated URLs, and secure-only cookies below would never be set).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# FERNET_KEY encrypts Bot.token_encrypted (CLAUDE.md §5). Never log or commit it.
FERNET_KEY = env("FERNET_KEY")

REDIS_URL = env("REDIS_URL")

# Separate logical DB from Celery's broker/result-backend above (same Redis
# instance, different DB index) so a cache flush can't ever touch queued
# tasks and vice versa. Django's cache framework has had a native Redis
# backend since 4.0 — no extra dependency (django-redis) needed, and the
# `redis` client package is already required for Celery's broker.
CACHES = {
    "default": env.cache("DJANGO_CACHE_URL", default=REDIS_URL.rsplit("/", 1)[0] + "/1"),
}

# Public HTTPS base URL Telegram will POST webhooks to (CLAUDE.md §7a). Telegram
# requires HTTPS, so local dev needs a tunnel (e.g. ngrok) pointed at this host.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="https://example.com")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.tenants",
    "apps.accounts",
    "apps.customers",
    "apps.ledger",
    "apps.seller_web",
    "apps.bot",
    "apps.broadcasts",
    "apps.audit",
]

# Session-based browser login used by the seller-web register page
# (CLAUDE.md §7b) — distinct from the JWT API used by the admin panel.
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "seller_web:register"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.tenants.middleware.TenantMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Broadcast media (images/videos attached to a tenant's Xabarnomalar).
# MEDIA_URL is intentionally never wired into urlpatterns for direct static
# serving — that would bypass tenant isolation (CLAUDE.md §4). The only way
# to read a file back is apps.broadcasts.api_views.BroadcastMediaFileView,
# which goes through the tenant-filtered BroadcastMedia manager first.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.tenants.authentication.CachingJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    # Audit finding H-3: without these two, nothing could ever revoke a
    # JWT before its own expiry — not a password change, not an explicit
    # logout. BLACKLIST_AFTER_ROTATION makes each refresh single-use (the
    # rest_framework_simplejwt.token_blacklist app above is what actually
    # enforces this — RefreshToken checks the blacklist automatically once
    # that app is installed). CHECK_REVOKE_TOKEN makes CachingJWTAuthentication's
    # existing (previously dead) check in apps/tenants/authentication.py
    # actually run: every token minted after this change carries an
    # `hash_password` claim, checked against the user's *current* password
    # hash on every request, so changing a password immediately invalidates
    # every outstanding access token for that user, not just future logins.
    #
    # One-time deploy consequence, not a bug: every token issued *before*
    # this change lacks that claim, so every currently-logged-in session
    # (admin/tenant_admin/seller JWT sessions) will see one 401 and need to
    # log in again the moment this ships — see apps/accounts/views.py's
    # logout endpoint for the explicit-logout half of this fix.
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
}

# Django's own default LOGGING only sends unhandled-exception tracebacks to
# `mail_admins` when DEBUG=False (its `console` handler is filtered to
# require_debug_true) — with no ADMINS/email backend configured, that means
# every production 500 vanishes silently instead of appearing in `docker
# compose logs web`. Route it to stdout unconditionally instead, at INFO so
# uvicorn's request-level warnings (4xx client errors DRF logs at INFO) show
# up too, not just crashes.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Celery (CLAUDE.md §9: notifications, broadcasts throttled to Telegram's ~25 msg/sec)
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# CLAUDE.md §8: daily per-seller summary. 21:00 Tashkent time = roughly end
# of a pharmacy's business day; adjust per real operating hours later.
CELERY_BEAT_SCHEDULE = {
    "send-daily-seller-summaries": {
        "task": "apps.ledger.tasks.send_daily_seller_summaries",
        "schedule": crontab(hour=21, minute=0),
    },
}
