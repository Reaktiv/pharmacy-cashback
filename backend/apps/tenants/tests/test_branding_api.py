import base64
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import UserProfile
from apps.tenants.models import Bot, GlobalSettings

TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _make_bot(tenant):
    bot_row = Bot.objects.all_tenants().create(tenant=tenant, username="@testbot")
    bot_row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    bot_row.save()
    return bot_row


@pytest.mark.django_db
def test_tenant_admin_can_rename_their_own_pharmacy(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(f"/api/tenants/{tenant.id}/", {"name": "Yangi Nom"}, format="json")

    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.name == "Yangi Nom"


@pytest.mark.django_db
def test_renaming_a_tenant_with_a_bot_schedules_a_display_name_sync(
    api_client_for, make_user, make_tenant, django_capture_on_commit_callbacks
):
    tenant = make_tenant("a")
    bot = _make_bot(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    with patch("apps.bot.tasks.sync_bot_display_name.delay") as mock_delay:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.patch(
                f"/api/tenants/{tenant.id}/", {"name": "Yangi Nom"}, format="json"
            )

    assert response.status_code == 200
    mock_delay.assert_called_once_with(bot.id, "Yangi Nom")


@pytest.mark.django_db
def test_renaming_a_tenant_without_a_bot_does_not_schedule_anything(
    api_client_for, make_user, make_tenant, django_capture_on_commit_callbacks
):
    tenant = make_tenant("a")  # no Bot row
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    with patch("apps.bot.tasks.sync_bot_display_name.delay") as mock_delay:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.patch(
                f"/api/tenants/{tenant.id}/", {"name": "Yangi Nom"}, format="json"
            )

    assert response.status_code == 200
    mock_delay.assert_not_called()


@pytest.mark.django_db
def test_not_renaming_does_not_schedule_a_sync(
    api_client_for, make_user, make_tenant, django_capture_on_commit_callbacks
):
    tenant = make_tenant("a")
    _make_bot(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    with patch("apps.bot.tasks.sync_bot_display_name.delay") as mock_delay:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.patch(
                f"/api/tenants/{tenant.id}/", {"cashback_rate": "9.00"}, format="json"
            )

    assert response.status_code == 200
    mock_delay.assert_not_called()


@pytest.mark.django_db
def test_tenant_admin_can_upload_a_logo(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    logo = SimpleUploadedFile("logo.png", TINY_PNG_BYTES, content_type="image/png")

    response = client.patch(f"/api/tenants/{tenant.id}/", {"logo": logo}, format="multipart")

    assert response.status_code == 200
    assert response.data["has_logo"] is True
    tenant.refresh_from_db()
    assert bool(tenant.logo) is True


@pytest.mark.django_db
def test_tenant_logo_upload_rejects_non_image(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    bad_file = SimpleUploadedFile("logo.txt", b"not an image", content_type="text/plain")

    response = client.patch(f"/api/tenants/{tenant.id}/", {"logo": bad_file}, format="multipart")

    assert response.status_code == 400


@pytest.mark.django_db
def test_tenant_admin_can_remove_their_logo(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    logo = SimpleUploadedFile("logo.png", TINY_PNG_BYTES, content_type="image/png")
    client.patch(f"/api/tenants/{tenant.id}/", {"logo": logo}, format="multipart")

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"remove_logo": "true"}, format="multipart"
    )

    assert response.status_code == 200
    assert response.data["has_logo"] is False


@pytest.mark.django_db
def test_tenant_admin_and_branch_manager_can_both_fetch_their_tenant_logo(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("a")
    branch = make_branch(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    admin_client = api_client_for(admin)
    manager_client = api_client_for(manager)
    logo = SimpleUploadedFile("logo.png", TINY_PNG_BYTES, content_type="image/png")
    admin_client.patch(f"/api/tenants/{tenant.id}/", {"logo": logo}, format="multipart")

    assert admin_client.get("/api/me/tenant-logo/").status_code == 200
    assert manager_client.get("/api/me/tenant-logo/").status_code == 200


@pytest.mark.django_db
def test_me_tenant_logo_404s_when_tenant_has_no_logo(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    assert client.get("/api/me/tenant-logo/").status_code == 404


@pytest.mark.django_db
def test_superadmin_can_set_platform_name_and_logo_via_me(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)
    logo = SimpleUploadedFile("logo.png", TINY_PNG_BYTES, content_type="image/png")

    response = client.patch(
        "/api/me/",
        {"platform_name": "Yangi Brend", "platform_logo": logo},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data["platform_name"] == "Yangi Brend"
    assert response.data["platform_has_logo"] is True
    gs = GlobalSettings.load()
    assert gs.platform_name == "Yangi Brend"
    assert bool(gs.platform_logo) is True


@pytest.mark.django_db
def test_non_superadmin_cannot_change_platform_branding_via_me(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    original_name = GlobalSettings.load().platform_name

    response = client.patch("/api/me/", {"platform_name": "Hijacked"}, format="json")

    assert response.status_code == 200
    assert GlobalSettings.load().platform_name == original_name


@pytest.mark.django_db
def test_non_superadmin_me_response_has_no_platform_name(api_client_for, make_user, make_tenant):
    tenant = make_tenant("a")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.get("/api/me/")

    assert response.data["platform_name"] is None
    assert response.data["platform_has_logo"] is None


@pytest.mark.django_db
def test_public_branding_endpoint_requires_no_auth(client):
    response = client.get("/api/branding/")

    assert response.status_code == 200
    assert response.data["name"] == "Pharmacy Cashback"
    assert response.data["has_logo"] is False


@pytest.mark.django_db
def test_public_branding_logo_404s_when_unset(client):
    assert client.get("/api/branding/logo/").status_code == 404


@pytest.mark.django_db
def test_public_branding_reflects_superadmin_changes(api_client_for, make_user, client):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    api_client = api_client_for(superadmin)
    api_client.patch("/api/me/", {"platform_name": "Rebranded"}, format="json")

    response = client.get("/api/branding/")

    assert response.data["name"] == "Rebranded"
