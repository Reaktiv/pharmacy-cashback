from decimal import Decimal

import pytest

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
def test_tenant_admin_cannot_create_tenants(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/tenants/", {"name": "New", "slug": "new", "cashback_rate": "5.00"}, format="json"
    )

    assert response.status_code == 403


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
