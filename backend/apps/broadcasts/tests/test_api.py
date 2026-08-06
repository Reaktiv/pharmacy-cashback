from unittest.mock import patch

import pytest

from apps.accounts.models import UserProfile
from apps.broadcasts.models import Broadcast


@pytest.mark.django_db
def test_tenant_admin_can_create_a_draft_broadcast(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/broadcasts/", {"title": "Sale!", "body": "20% off today."}, format="json"
    )

    assert response.status_code == 201
    broadcast = Broadcast.objects.all_tenants().get(pk=response.data["id"])
    assert broadcast.tenant_id == tenant.id
    assert broadcast.created_by_id == admin.id
    assert broadcast.status == Broadcast.Status.DRAFT


@pytest.mark.django_db
def test_tenant_admin_only_sees_their_own_broadcasts(api_client_for, make_user, make_tenant):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    admin_b = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)
    Broadcast.objects.all_tenants().create(
        tenant=tenant_a, title="A", body="a", created_by=admin_a
    )
    Broadcast.objects.all_tenants().create(
        tenant=tenant_b, title="B", body="b", created_by=admin_b
    )
    client = api_client_for(admin_a)

    response = client.get("/api/broadcasts/")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    assert rows[0]["title"] == "A"


@pytest.mark.django_db
def test_sending_a_broadcast_enqueues_the_task(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )
    client = api_client_for(admin)

    with patch("apps.broadcasts.api_views.send_broadcast") as mock_task:
        response = client.post(f"/api/broadcasts/{broadcast.pk}/send/")

    assert response.status_code == 200
    mock_task.delay.assert_called_once_with(broadcast.pk)


@pytest.mark.django_db
def test_sending_an_already_sent_broadcast_is_rejected(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin, status=Broadcast.Status.SENT
    )
    client = api_client_for(admin)

    with patch("apps.broadcasts.api_views.send_broadcast") as mock_task:
        response = client.post(f"/api/broadcasts/{broadcast.pk}/send/")

    assert response.status_code == 400
    mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_seller_cannot_access_broadcasts(api_client_for, make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)
    client = api_client_for(seller)

    response = client.get("/api/broadcasts/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_broadcast_body_is_sanitized_to_the_telegram_safe_subset(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/broadcasts/",
        {
            "title": "Sale!",
            "body": (
                "<script>alert(1)</script>"
                "<div>Hello <strong>world</strong></div>"
                '<a href="javascript:x">bad</a>'
            ),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    broadcast = Broadcast.objects.all_tenants().get(pk=response.data["id"])
    assert "<script>" not in broadcast.body
    assert "alert(1)" not in broadcast.body
    assert "<b>world</b>" in broadcast.body
    assert "javascript:" not in broadcast.body


@pytest.mark.django_db
def test_broadcast_body_over_text_only_limit_is_rejected(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/broadcasts/", {"title": "Sale!", "body": "a" * 4090}, format="json"
    )

    assert response.status_code == 400
    assert "body" in response.data


@pytest.mark.django_db
def test_broadcast_body_within_text_only_limit_is_accepted(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/broadcasts/", {"title": "Sale!", "body": "a" * 100}, format="json"
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_broadcast_body_over_media_caption_limit_is_rejected(
    api_client_for, make_user, make_tenant
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    upload = client.post(
        "/api/broadcast-media/",
        {"file": SimpleUploadedFile("pic.png", b"x" * 10, content_type="image/png")},
        format="multipart",
    )
    media_id = upload.data["id"]

    response = client.post(
        "/api/broadcasts/",
        {"title": "Sale!", "body": "a" * 1050, "media_id": media_id},
        format="json",
    )

    assert response.status_code == 400
    assert "body" in response.data


@pytest.mark.django_db
def test_broadcast_body_within_media_caption_limit_is_accepted(
    api_client_for, make_user, make_tenant
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    upload = client.post(
        "/api/broadcast-media/",
        {"file": SimpleUploadedFile("pic.png", b"x" * 10, content_type="image/png")},
        format="multipart",
    )
    media_id = upload.data["id"]

    response = client.post(
        "/api/broadcasts/",
        {"title": "Sale!", "body": "a" * 100, "media_id": media_id},
        format="json",
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_only_draft_broadcasts_can_be_edited(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin, status=Broadcast.Status.SENT
    )

    response = client.patch(f"/api/broadcasts/{broadcast.pk}/", {"title": "New"}, format="json")

    assert response.status_code == 400
