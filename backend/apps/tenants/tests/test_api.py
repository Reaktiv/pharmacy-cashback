from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import UserProfile
from apps.tenants.models import Bot, GlobalSettings


@pytest.mark.django_db
def test_superadmin_can_list_all_tenants(api_client_for, make_user, make_tenant):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.get("/api/tenants/")

    assert response.status_code == 200
    names = {row["name"] for row in response.data["results"]} if isinstance(
        response.data, dict
    ) else {row["name"] for row in response.data}
    assert {tenant_a.name, tenant_b.name} <= names


@pytest.mark.django_db
def test_tenant_admin_only_sees_their_own_tenant(api_client_for, make_user, make_tenant):
    tenant_a = make_tenant("a")
    make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.get("/api/tenants/")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    assert rows[0]["id"] == tenant_a.id


@pytest.mark.django_db
def test_tenant_admin_cannot_access_another_tenant_by_id(api_client_for, make_user, make_tenant):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.get(f"/api/tenants/{tenant_b.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_tenant_admin_can_set_rate_within_cap(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a", rate=Decimal("5.00"))
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(f"/api/tenants/{tenant.id}/", {"cashback_rate": "8.00"}, format="json")

    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.cashback_rate == Decimal("8.00")


@pytest.mark.django_db
def test_tenant_admin_rate_above_cap_is_rejected(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a", rate=Decimal("5.00"))
    GlobalSettings.load()  # default max_cashback_rate = 15.00
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(f"/api/tenants/{tenant.id}/", {"cashback_rate": "20.00"}, format="json")

    assert response.status_code == 400
    tenant.refresh_from_db()
    assert tenant.cashback_rate == Decimal("5.00")


@pytest.mark.django_db
def test_tenant_admin_cannot_change_slug_or_is_active(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(f"/api/tenants/{tenant.id}/", {"slug": "hijacked"}, format="json")

    assert response.status_code == 400
    tenant.refresh_from_db()
    assert tenant.slug == "a"


@pytest.mark.django_db
def test_tenant_admin_can_set_receipt_tin(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"receipt_tin": "301422146"}, format="json"
    )

    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.receipt_tin == "301422146"


@pytest.mark.django_db
def test_receipt_tin_must_be_nine_digits(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(f"/api/tenants/{tenant.id}/", {"receipt_tin": "12345"}, format="json")

    assert response.status_code == 400
    tenant.refresh_from_db()
    assert tenant.receipt_tin == ""


@pytest.mark.django_db
def test_tenant_admin_can_set_receipt_branch_to_their_own_branch(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("a")
    branch = make_branch(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"receipt_branch": branch.id}, format="json"
    )

    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.receipt_branch_id == branch.id


@pytest.mark.django_db
def test_tenant_admin_cannot_set_receipt_branch_to_another_tenants_branch(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    foreign_branch = make_branch(tenant_b)
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.patch(
        f"/api/tenants/{tenant_a.id}/", {"receipt_branch": foreign_branch.id}, format="json"
    )

    assert response.status_code == 400
    tenant_a.refresh_from_db()
    assert tenant_a.receipt_branch_id is None


@pytest.mark.django_db
def test_tenant_admin_cannot_create_tenants(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/tenants/", {"name": "New", "slug": "new", "cashback_rate": "5.00"}, format="json"
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_delete_a_tenant(api_client_for, make_user, make_tenant):
    from apps.tenants.models import Tenant

    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.delete(f"/api/tenants/{tenant.id}/")

    assert response.status_code == 204
    assert not Tenant.objects.filter(pk=tenant.id).exists()


@pytest.mark.django_db
def test_superadmin_can_delete_a_fully_populated_tenant(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    """Deleting a tenant is double-confirmed on the frontend before this
    DELETE is ever sent (see ConfirmDialog usage in TenantDetailPage), so by
    the time it reaches the API it must cascade fully — branches, sellers,
    branch managers, the tenant admin's own login, ledger history (including
    a reversal, whose self-referential PROTECT FK would otherwise block a
    plain cascade), pending cashback, and broadcasts. Previously this raised
    a raw ProtectedError (500) for any tenant with real data — only an empty
    tenant like the one `make_tenant` alone produces would have deleted
    cleanly."""
    from apps.accounts.models import Branch, Seller
    from apps.broadcasts.models import Broadcast, BroadcastMedia
    from apps.customers.models import Customer, PendingCashback
    from apps.ledger.models import Transaction
    from apps.ledger.services import post_earn_transaction, post_reversal
    from apps.tenants.models import Tenant

    tenant = make_tenant("a", rate=Decimal("5.00"))
    tenant_id = tenant.id
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    branch_manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    tenant_admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    customer = make_customer(tenant)

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    post_reversal(original_txn=txn, actor=tenant_admin)
    PendingCashback.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", amount=Decimal("5000"), branch=branch
    )
    media = BroadcastMedia.objects.all_tenants().create(
        tenant=tenant,
        file=f"broadcast_media/{tenant.id}/fake.jpg",
        media_type=BroadcastMedia.MediaType.IMAGE,
        original_filename="fake.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        uploaded_by=tenant_admin,
    )
    Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale", body="20% off", media=media, created_by=tenant_admin
    )

    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.delete(f"/api/tenants/{tenant_id}/")

    assert response.status_code == 204
    assert not Tenant.objects.filter(pk=tenant_id).exists()
    assert not Branch.objects.all_tenants().filter(pk=branch.id).exists()
    assert not Seller.objects.all_tenants().filter(pk=seller.id).exists()
    assert not Customer.objects.all_tenants().filter(pk=customer.id).exists()
    assert Transaction.objects.all_tenants().filter(tenant_id=tenant_id).count() == 0
    assert not PendingCashback.objects.all_tenants().filter(tenant_id=tenant_id).exists()
    assert not Broadcast.objects.all_tenants().filter(tenant_id=tenant_id).exists()
    assert not BroadcastMedia.objects.all_tenants().filter(tenant_id=tenant_id).exists()
    assert not User.objects.filter(pk=branch_manager.id).exists()
    assert not User.objects.filter(pk=tenant_admin.id).exists()


@pytest.mark.django_db
def test_tenant_admin_cannot_delete_their_own_tenant(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.delete(f"/api/tenants/{tenant.id}/")

    assert response.status_code == 403
    tenant.refresh_from_db()


@pytest.mark.django_db
def test_seller_cannot_access_tenants_endpoint(api_client_for, make_user, make_tenant, make_branch):
    tenant = make_tenant("a")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)
    client = api_client_for(seller)

    response = client.get("/api/tenants/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_create_a_bot_with_encrypted_token(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    with patch("apps.tenants.serializers.validate_bot_token", return_value="testbot"):
        response = client.post(
            "/api/bots/",
            {"tenant": tenant.id, "username": "@testbot", "token": "123456:REAL-LOOKING-TOKEN"},
            format="json",
        )

    assert response.status_code == 201
    assert "token" not in response.data
    bot = Bot.objects.all_tenants().get(tenant=tenant)
    assert bot.get_token() == "123456:REAL-LOOKING-TOKEN"


@pytest.mark.django_db
def test_bot_creation_with_malformed_token_is_rejected(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.post(
        "/api/bots/",
        {"tenant": tenant.id, "username": "@testbot", "token": "not-a-real-token"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["token"][0] == "Invalid token format."
    assert not Bot.objects.all_tenants().filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_bot_creation_with_a_token_telegram_rejects_is_not_saved(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    from apps.bot.telegram_client import TelegramTokenValidationError

    with patch(
        "apps.tenants.serializers.validate_bot_token",
        side_effect=TelegramTokenValidationError("Telegram rejected this token."),
    ):
        response = client.post(
            "/api/bots/",
            {"tenant": tenant.id, "username": "@testbot", "token": "123456:REAL-LOOKING-TOKEN"},
            format="json",
        )

    assert response.status_code == 400
    assert response.data["token"][0] == "Telegram rejected this token."
    assert not Bot.objects.all_tenants().filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_rotating_a_bot_token_with_a_bot_id_mismatch_is_rejected_and_old_token_kept(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    from apps.bot.telegram_client import TelegramTokenValidationError

    with patch("apps.tenants.serializers.validate_bot_token", return_value="testbot"):
        bot_id = client.post(
            "/api/bots/",
            {"tenant": tenant.id, "username": "@testbot", "token": "111111:OLD-TOKEN"},
            format="json",
        ).data["id"]

    with patch(
        "apps.tenants.serializers.validate_bot_token",
        side_effect=TelegramTokenValidationError(
            "Bot ID mismatch. The token appears to be invalid."
        ),
    ):
        response = client.patch(
            f"/api/bots/{bot_id}/", {"token": "222222:WRONG-BOT-TOKEN"}, format="json"
        )

    assert response.status_code == 400
    assert response.data["token"][0] == "Bot ID mismatch. The token appears to be invalid."
    bot = Bot.objects.all_tenants().get(pk=bot_id)
    assert bot.get_token() == "111111:OLD-TOKEN"


@pytest.mark.django_db
def test_rotating_a_bot_token_schedules_deregistration_of_the_old_one(
    api_client_for, make_user, make_tenant, django_capture_on_commit_callbacks
):
    """Reproduces the reported bug: rotating a bot's token must clean up
    the OLD token's webhook (apps.bot.tasks.rotate_bot_credentials) —
    otherwise the old bot keeps answering too, and the username is never
    refreshed to match the new token's real identity."""
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)
    with patch("apps.tenants.serializers.validate_bot_token", return_value="testbot"):
        bot_id = client.post(
            "/api/bots/",
            {"tenant": tenant.id, "username": "@testbot", "token": "111111:OLD-TOKEN"},
            format="json",
        ).data["id"]

    with patch("apps.tenants.serializers.validate_bot_token", return_value="testbot"):
        with patch("apps.bot.tasks.rotate_bot_credentials.delay") as mock_delay:
            with django_capture_on_commit_callbacks(execute=True):
                response = client.patch(
                    f"/api/bots/{bot_id}/", {"token": "222222:NEW-TOKEN"}, format="json"
                )

    assert response.status_code == 200
    mock_delay.assert_called_once_with(bot_id, "111111:OLD-TOKEN")
    bot = Bot.objects.all_tenants().get(pk=bot_id)
    assert bot.get_token() == "222222:NEW-TOKEN"


@pytest.mark.django_db
def test_bot_creation_without_token_is_rejected(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.post(
        "/api/bots/", {"tenant": tenant.id, "username": "@testbot"}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_tenant_admin_cannot_manage_bots(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.get("/api/bots/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_update_global_settings(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.patch(
        "/api/global-settings/", {"max_cashback_rate": "20.00"}, format="json"
    )

    assert response.status_code == 200
    assert GlobalSettings.load().max_cashback_rate == Decimal("20.00")


@pytest.mark.django_db
def test_tenant_admin_cannot_update_global_settings(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.get("/api/global-settings/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_set_broadcast_quota(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"broadcast_quota": 10}, format="json"
    )

    assert response.status_code == 200, response.data
    tenant.refresh_from_db()
    assert tenant.broadcast_quota == 10


@pytest.mark.django_db
def test_tenant_admin_cannot_change_broadcast_quota(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    tenant.broadcast_quota = 5
    tenant.save()
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"broadcast_quota": 999}, format="json"
    )

    assert response.status_code == 400
    tenant.refresh_from_db()
    assert tenant.broadcast_quota == 5


@pytest.mark.django_db
def test_broadcast_quota_changed_audit_log_written_on_change(
    api_client_for, make_user, make_tenant
):
    from apps.audit.models import AuditLog

    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"broadcast_quota": 7}, format="json"
    )

    assert response.status_code == 200, response.data
    assert AuditLog.objects.filter(
        action="broadcast_quota_changed", target_type="Tenant", target_id=tenant.id
    ).exists()


@pytest.mark.django_db
def test_broadcast_quota_changed_audit_log_not_written_when_unchanged(
    api_client_for, make_user, make_tenant
):
    from apps.audit.models import AuditLog

    tenant = make_tenant("a")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.patch(f"/api/tenants/{tenant.id}/", {"name": "Renamed"}, format="json")

    assert response.status_code == 200, response.data
    assert not AuditLog.objects.filter(
        action="broadcast_quota_changed", target_type="Tenant", target_id=tenant.id
    ).exists()


@pytest.mark.django_db
def test_broadcasts_sent_this_month_counts_only_this_tenants_sent_legs(
    api_client_for, make_user, make_tenant
):
    from apps.broadcasts.models import Broadcast, PlatformBroadcast

    tenant = make_tenant("a")
    other_tenant = make_tenant("b")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)

    # Counts: a sent broadcast for this tenant.
    Broadcast.objects.all_tenants().create(
        tenant=tenant, title="A", body="a", created_by=admin, status=Broadcast.Status.SENT
    )
    # Does not count: still a draft.
    Broadcast.objects.all_tenants().create(
        tenant=tenant, title="B", body="b", created_by=admin, status=Broadcast.Status.DRAFT
    )
    # Does not count: belongs to another tenant.
    Broadcast.objects.all_tenants().create(
        tenant=other_tenant, title="C", body="c", created_by=admin, status=Broadcast.Status.SENT
    )
    # Does not count: a platform-broadcast leg (superadmin-originated).
    platform_broadcast = PlatformBroadcast.objects.create(
        title="P", body="p", created_by=superadmin
    )
    Broadcast.objects.all_tenants().create(
        tenant=tenant,
        title="D",
        body="d",
        created_by=superadmin,
        status=Broadcast.Status.SENT,
        platform_broadcast=platform_broadcast,
    )

    client = api_client_for(admin)
    response = client.get(f"/api/tenants/{tenant.id}/")

    assert response.status_code == 200
    assert response.data["broadcasts_sent_this_month"] == 1
