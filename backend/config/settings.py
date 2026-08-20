"""
Django settings for the Pharmacy Cashback SaaS platform.

See CLAUDE.md §9 for the tech stack and conventions this file implements.
"""

import logging
import time
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

# apps.bot.tasks._fetch_receipt_via_playwright's only consumer:
# ofd.soliq.uz (O'zbekiston's fiscal receipt lookup) silently drops TCP
# connections from outside Uzbekistan — confirmed by hand (curl/raw TCP
# connect from a France-hosted VPS times out at the handshake, 0/2 on
# retry, while general internet access from that same server is fine and
# the same URL resolves instantly from an Uzbek ISP). A server hosted
# outside Uzbekistan therefore needs an Uzbek egress point for this one
# outbound call specifically — everything else the app does is unaffected
# and keeps using the server's normal network path directly. Empty (the
# default) preserves that direct-connection behavior exactly as it was
# before this setting existed. Format: any value Playwright's own `proxy`
# launch option accepts as `server`, e.g. "http://host:port" or
# "socks5://host:port" (+ OFD_PROXY_USERNAME/OFD_PROXY_PASSWORD below if
# the proxy requires auth).
OFD_PROXY_URL = env("OFD_PROXY_URL", default="")
OFD_PROXY_USERNAME = env("OFD_PROXY_USERNAME", default="")
OFD_PROXY_PASSWORD = env("OFD_PROXY_PASSWORD", default="")

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
#
# Any app's own logger.info()/.warning() calls (logging.getLogger(__name__)
# under apps.*, e.g. apps/bot/handlers.py's receipt-QR telemetry or apps/
# ledger/tasks.py's daily seller summary) were going nowhere without an
# entry here: with no matching logger configured, they propagate to the
# root logger, which dictConfig leaves with zero handlers and Python's
# default WARNING level. INFO records were silently dropped before ever
# reaching a handler; WARNING records only surfaced via logging.lastResort,
# an untimestamped stderr fallback with no level/logger-name prefix —
# undocumented, not something to build a log parser against (see apps/bot/
# management/commands/receipt_qr_report.py).
#
# This is keyed on "apps", not "apps.bot" — a per-app entry was tried first
# and had to be reverted: it fixes exactly the one app someone remembered to
# add and leaves every other apps.* module (apps.ledger, apps.tenants, ...)
# in the same silently-handler-less state, which is the same shape of bug
# as the receipt-QR path had twice over (a client-supplied MIME allowlist,
# then an exact-format allowlist) — a hand-maintained list that silently
# drops whatever nobody remembered to add. Python's logger hierarchy is
# dotted-name-prefix based, so one entry on the "apps" parent covers every
# apps.* logger project-wide, present or future, with no per-app step to
# remember. Verified: a handler on "apps" receives records from both
# apps.bot.qr and apps.ledger.tasks, and does NOT receive django.request —
# the scope is exactly the project's own code, not Django's or a
# third-party library's.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "apps_console": {
            "()": "logging.Formatter",
            "format": "%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
        "apps_console": {
            "class": "logging.StreamHandler",
            "formatter": "apps_console",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["apps_console"],
            "level": "INFO",
            # True, unlike "django" above: root has no handlers of its own
            # configured here, so letting the record propagate past
            # apps_console doesn't risk a duplicate line — it just also lets
            # pytest's caplog fixture see these records (it captures via a
            # handler it attaches to the root logger; propagate=False would
            # stop every apps.* record at this logger and never reach it,
            # breaking every caplog-based test in every app).
            "propagate": True,
        },
    },
}
# %(asctime)s above renders in whatever time.localtime() reports, which is
# only UTC because containers happen to run with no TZ set — pin it
# explicitly rather than relying on that. This is a process-wide effect on
# every logging.Formatter (there's no per-formatter way to set it via
# dictConfig), which is fine here: no other formatter in this project sets a
# format string that includes asctime at all, so nothing else's output
# changes.
logging.Formatter.converter = time.gmtime

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
