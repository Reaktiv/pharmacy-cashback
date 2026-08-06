"""Regression test for the TenantContextError admin bug: Django admin builds
FK dropdown fields via `formfield_for_foreignkey`, which — for any FK
pointing at a TenantScopedModel — used to crash for superadmins (no tenant
bound to their request context) even though `get_queryset()` was already
correctly routed through `.all_tenants()`. See TenantScopedAdminMixin.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(username="root", password="pass1234")


@pytest.fixture
def admin_client(superuser):
    client = Client()
    client.force_login(superuser)
    return client


@pytest.mark.parametrize(
    "url",
    [
        "/admin/accounts/branch/add/",
        "/admin/accounts/seller/add/",
        "/admin/accounts/userprofile/add/",
        "/admin/broadcasts/broadcast/add/",
        "/admin/customers/customer/add/",
        "/admin/customers/pendingcashback/add/",
        "/admin/customers/otp/add/",
        "/admin/ledger/transaction/add/",
        "/admin/tenants/bot/add/",
    ],
)
def test_admin_add_view_does_not_raise_for_superadmin(admin_client, url):
    response = admin_client.get(url)
    assert response.status_code == 200


def test_admin_can_save_a_new_bot(admin_client, make_tenant):
    """POST hits a second instance of the same underlying bug:
    Model.full_clean() -> validate_unique() queries Bot's own default
    manager directly, independent of formfield_for_foreignkey."""
    tenant = make_tenant("bot-save-tenant")
    with patch("apps.tenants.admin.validate_bot_token", return_value="save_test_bot"):
        response = admin_client.post(
            "/admin/tenants/bot/add/",
            {
                "tenant": tenant.id,
                "username": "@save_test_bot",
                "token": "123456:FAKE-TOKEN-FOR-TEST",
                "is_active": "on",
            },
        )
    assert response.status_code == 302, getattr(response, "context", None) and response.context[
        "adminform"
    ].form.errors
    from apps.tenants.models import Bot

    assert Bot.objects.all_tenants().filter(tenant=tenant, username="@save_test_bot").exists()


def test_admin_rejects_a_malformed_bot_token(admin_client, make_tenant):
    # No mocking here: format validation short-circuits before any Telegram
    # call (see validate_bot_token / test_telegram_client.py), so this is
    # safe to run against the real function.
    tenant = make_tenant("bot-bad-format-tenant")
    response = admin_client.post(
        "/admin/tenants/bot/add/",
        {
            "tenant": tenant.id,
            "username": "@bad_format_bot",
            "token": "not-a-real-token",
            "is_active": "on",
        },
    )
    assert response.status_code == 200
    assert "Invalid token format." in response.context["adminform"].form.errors["token"]
    from apps.tenants.models import Bot

    assert not Bot.objects.all_tenants().filter(tenant=tenant).exists()


def test_admin_rejects_a_bot_token_telegram_rejects(admin_client, make_tenant):
    from apps.bot.telegram_client import TelegramTokenValidationError

    tenant = make_tenant("bot-rejected-tenant")
    with patch(
        "apps.tenants.admin.validate_bot_token",
        side_effect=TelegramTokenValidationError("Telegram rejected this token."),
    ):
        response = admin_client.post(
            "/admin/tenants/bot/add/",
            {
                "tenant": tenant.id,
                "username": "@rejected_bot",
                "token": "123456:REAL-LOOKING-TOKEN",
                "is_active": "on",
            },
        )
    assert response.status_code == 200
    assert "Telegram rejected this token." in response.context["adminform"].form.errors["token"]
    from apps.tenants.models import Bot

    assert not Bot.objects.all_tenants().filter(tenant=tenant).exists()


def test_admin_can_save_a_new_seller(admin_client, make_tenant, make_branch, make_user):
    tenant = make_tenant("seller-save-tenant")
    branch = make_branch(tenant)
    user = make_user(username="seller_save_user")
    response = admin_client.post(
        "/admin/accounts/seller/add/",
        {
            "tenant": tenant.id,
            "branch": branch.id,
            "user": user.id,
            "phone": "+998900001111",
            "full_name": "Saved Seller",
            "is_active": "on",
        },
    )
    assert response.status_code == 302, getattr(response, "context", None) and response.context[
        "adminform"
    ].form.errors
    from apps.accounts.models import Seller

    assert Seller.objects.all_tenants().filter(tenant=tenant, full_name="Saved Seller").exists()
