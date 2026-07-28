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
