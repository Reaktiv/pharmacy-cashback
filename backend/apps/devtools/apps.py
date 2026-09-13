from django.apps import AppConfig


class DevtoolsConfig(AppConfig):
    """No models — exists only to hold the `runserver` override (see
    management/commands/runserver.py) and win Django's command-name
    resolution over django.contrib.staticfiles's own `runserver`. Must be
    listed before 'django.contrib.staticfiles' in INSTALLED_APPS for that
    override to take effect (Django resolves name collisions in favor of
    whichever app appears earliest in INSTALLED_APPS)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.devtools"
    label = "devtools"
