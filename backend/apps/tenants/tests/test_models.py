from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.tenants.models import Bot, GlobalSettings, Tenant


@pytest.mark.django_db
def test_tenant_rate_within_global_cap_is_valid():
    GlobalSettings.load()  # default max_cashback_rate = 15.00
    tenant = Tenant(name="Dorimed", slug="dorimed", cashback_rate=Decimal("10.00"))
    tenant.full_clean()  # must not raise


@pytest.mark.django_db
def test_tenant_rate_above_global_cap_is_rejected():
    GlobalSettings.load()  # default max_cashback_rate = 15.00
    tenant = Tenant(name="Dorimed", slug="dorimed", cashback_rate=Decimal("20.00"))
    with pytest.raises(ValidationError):
        tenant.full_clean()


@pytest.mark.django_db
def test_tenant_rate_at_exactly_the_cap_is_valid():
    settings = GlobalSettings.load()
    tenant = Tenant(name="Dorimed", slug="dorimed", cashback_rate=settings.max_cashback_rate)
    tenant.full_clean()  # must not raise — cap is inclusive


@pytest.mark.django_db
def test_lowering_the_global_cap_does_not_retroactively_touch_existing_tenants():
    settings = GlobalSettings.load()
    tenant = Tenant.objects.create(name="Dorimed", slug="dorimed", cashback_rate=Decimal("14.00"))

    settings.max_cashback_rate = Decimal("10.00")
    settings.save()

    tenant.refresh_from_db()
    # untouched; only future clean() calls are blocked
    assert tenant.cashback_rate == Decimal("14.00")
    with pytest.raises(ValidationError):
        tenant.full_clean()


@pytest.mark.django_db
def test_global_settings_is_a_singleton():
    first = GlobalSettings.load()
    second = GlobalSettings.load()

    assert first.pk == second.pk == 1
    assert GlobalSettings.objects.count() == 1


@pytest.mark.django_db
def test_global_settings_cannot_be_deleted():
    settings = GlobalSettings.load()
    with pytest.raises(RuntimeError):
        settings.delete()


@pytest.mark.django_db
def test_global_settings_load_is_cached_after_the_first_call(django_assert_num_queries):
    GlobalSettings.load()  # first call: cache miss, hits the DB

    with django_assert_num_queries(0):
        GlobalSettings.load()


@pytest.mark.django_db
def test_saving_global_settings_invalidates_the_cache(django_assert_num_queries):
    settings = GlobalSettings.load()
    settings.max_cashback_rate = Decimal("7.00")
    settings.save()

    with django_assert_num_queries(1):
        reloaded = GlobalSettings.load()
    assert reloaded.max_cashback_rate == Decimal("7.00")


@pytest.mark.django_db
def test_bot_token_is_never_stored_in_plaintext():
    tenant = Tenant.objects.create(name="Dorimed", slug="dorimed", cashback_rate=Decimal("5.00"))
    bot = Bot(tenant=tenant, username="@dorimed_bot")

    raw_token = "123456789:AAExampleRealLookingTelegramToken"
    bot.set_token(raw_token)

    assert raw_token not in bot.token_encrypted
    bot.save()

    stored = Bot.base_objects.get(pk=bot.pk)
    assert raw_token not in stored.token_encrypted
    assert stored.get_token() == raw_token
