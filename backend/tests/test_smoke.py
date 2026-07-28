import pytest


def test_settings_load():
    from django.conf import settings

    assert settings.ROOT_URLCONF == "config.urls"


@pytest.mark.django_db
def test_can_touch_the_database():
    from django.contrib.auth.models import User

    assert User.objects.count() == 0
