from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import UserProfile
from apps.broadcasts.models import Broadcast, PlatformBroadcast

NON_SUPERADMIN_ROLES = [
    UserProfile.Role.TENANT_ADMIN,
    UserProfile.Role.BRANCH_MANAGER,
    UserProfile.Role.SELLER,
]


def _make_non_superadmin(role, make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant) if role != UserProfile.Role.TENANT_ADMIN else None
    return make_user(role=role, tenant=tenant, branch=branch)


@pytest.mark.django_db
@pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
def test_non_superadmin_cannot_list_platform_broadcasts(
    role, api_client_for, make_user, make_tenant, make_branch
):
    user = _make_non_superadmin(role, make_user, make_tenant, make_branch)
    client = api_client_for(user)

    response = client.get("/api/platform-broadcasts/")

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
def test_non_superadmin_cannot_create_platform_broadcast(
    role, api_client_for, make_user, make_tenant, make_branch
):
    user = _make_non_superadmin(role, make_user, make_tenant, make_branch)
    client = api_client_for(user)

    response = client.post(
        "/api/platform-broadcasts/", {"title": "T", "body": "b"}, format="json"
    )

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
def test_non_superadmin_cannot_retrieve_platform_broadcast(
    role, api_client_for, make_user, make_tenant, make_branch
):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)
    user = _make_non_superadmin(role, make_user, make_tenant, make_branch)
    client = api_client_for(user)

    response = client.get(f"/api/platform-broadcasts/{pb.pk}/")

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
def test_non_superadmin_cannot_send_platform_broadcast(
    role, api_client_for, make_user, make_tenant, make_branch
):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)
    user = _make_non_superadmin(role, make_user, make_tenant, make_branch)
    client = api_client_for(user)

    response = client.post(f"/api/platform-broadcasts/{pb.pk}/send/")

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
def test_non_superadmin_cannot_upload_platform_broadcast_media(
    role, api_client_for, make_user, make_tenant, make_branch
):
    user = _make_non_superadmin(role, make_user, make_tenant, make_branch)
    client = api_client_for(user)

    response = client.post(
        "/api/platform-broadcast-media/",
        {"file": SimpleUploadedFile("pic.png", b"x" * 10, content_type="image/png")},
        format="multipart",
    )

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
def test_non_superadmin_cannot_read_platform_broadcast_media_file(
    role, api_client_for, make_user, make_tenant, make_branch
):
    from apps.broadcasts.models import PlatformBroadcastMedia

    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    media = PlatformBroadcastMedia.objects.create(
        file=SimpleUploadedFile("pic.png", b"x" * 10, content_type="image/png"),
        media_type=PlatformBroadcastMedia.MediaType.IMAGE,
        original_filename="pic.png",
        content_type="image/png",
        size_bytes=10,
        uploaded_by=superadmin,
    )
    user = _make_non_superadmin(role, make_user, make_tenant, make_branch)
    client = api_client_for(user)

    response = client.get(f"/api/platform-broadcast-media/{media.pk}/file/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_create_a_draft_platform_broadcast(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.post(
        "/api/platform-broadcasts/", {"title": "Announcement", "body": "Hello all"}, format="json"
    )

    assert response.status_code == 201, response.data
    pb = PlatformBroadcast.objects.get(pk=response.data["id"])
    assert pb.created_by_id == superadmin.id
    assert pb.status == PlatformBroadcast.Status.DRAFT


@pytest.mark.django_db
def test_sending_a_platform_broadcast_locks_flips_and_enqueues(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)
    client = api_client_for(superadmin)

    with patch("apps.broadcasts.api_views.send_platform_broadcast") as mock_task:
        response = client.post(f"/api/platform-broadcasts/{pb.pk}/send/")

    assert response.status_code == 200, response.data
    mock_task.delay.assert_called_once_with(pb.pk)
    pb.refresh_from_db()
    assert pb.status == PlatformBroadcast.Status.SENDING


@pytest.mark.django_db
def test_sending_an_already_sending_platform_broadcast_is_rejected(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    pb = PlatformBroadcast.objects.create(
        title="T", body="b", created_by=superadmin, status=PlatformBroadcast.Status.SENDING
    )
    client = api_client_for(superadmin)

    with patch("apps.broadcasts.api_views.send_platform_broadcast") as mock_task:
        response = client.post(f"/api/platform-broadcasts/{pb.pk}/send/")

    assert response.status_code == 400
    mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_platform_broadcast_list_reports_aggregated_counts_across_tenant_legs(
    api_client_for, make_user, make_tenant
):
    """Regression test for the tenant_legs manager trap: aggregation must be
    done via queryset annotation, not by touching `.tenant_legs` on an
    instance (which inherits Broadcast's tenant-scoped TenantManager and
    either raises TenantContextError or, via all_tenants(), silently returns
    every Broadcast row in the whole table)."""
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)
    Broadcast.objects.all_tenants().create(
        tenant=tenant_a,
        title="T",
        body="b",
        created_by=superadmin,
        platform_broadcast=pb,
        status=Broadcast.Status.SENT,
        sent_count=5,
        failed_count=1,
    )
    Broadcast.objects.all_tenants().create(
        tenant=tenant_b,
        title="T",
        body="b",
        created_by=superadmin,
        platform_broadcast=pb,
        status=Broadcast.Status.SENT,
        sent_count=3,
        failed_count=0,
    )
    # A normal tenant_admin broadcast, unrelated to this platform broadcast —
    # must not leak into the aggregate.
    Broadcast.objects.all_tenants().create(
        tenant=tenant_a, title="Unrelated", body="b", created_by=superadmin, sent_count=100
    )
    client = api_client_for(superadmin)

    response = client.get(f"/api/platform-broadcasts/{pb.pk}/")

    assert response.status_code == 200, response.data
    assert response.data["sent_count"] == 8
    assert response.data["failed_count"] == 1
    assert response.data["tenant_count"] == 2


@pytest.mark.django_db
def test_platform_broadcast_with_no_legs_reports_zero_counts(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)
    client = api_client_for(superadmin)

    response = client.get(f"/api/platform-broadcasts/{pb.pk}/")

    assert response.status_code == 200
    assert response.data["sent_count"] == 0
    assert response.data["failed_count"] == 0
    assert response.data["tenant_count"] == 0
