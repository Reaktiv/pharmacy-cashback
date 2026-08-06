import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import UserProfile
from apps.broadcasts.models import BroadcastMedia


def _tiny_png():
    return SimpleUploadedFile(
        "pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png"
    )


@pytest.mark.django_db
def test_tenant_admin_can_upload_an_image(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")

    assert response.status_code == 201, response.data
    assert response.data["media_type"] == "image"
    assert response.data["url"]
    media = BroadcastMedia.objects.all_tenants().get(pk=response.data["id"])
    assert media.tenant_id == tenant.id
    assert media.uploaded_by_id == admin.id
    assert media.original_filename == "pic.png"


@pytest.mark.django_db
def test_upload_rejects_unsupported_content_type(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    bad_file = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf")

    response = client.post("/api/broadcast-media/", {"file": bad_file}, format="multipart")

    assert response.status_code == 400
    assert "rasm yoki video" in str(response.data).lower()


@pytest.mark.django_db
def test_upload_rejects_oversized_video(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    # Real bytes, not a spoofed `.size` — Django's multipart parser rebuilds
    # the uploaded-file object from the actual request body, so a faked
    # attribute on the client-side object never survives the round trip.
    big_file = SimpleUploadedFile(
        "clip.mp4", b"0" * (51 * 1024 * 1024), content_type="video/mp4"
    )

    response = client.post("/api/broadcast-media/", {"file": big_file}, format="multipart")

    assert response.status_code == 400
    assert "50" in str(response.data)


@pytest.mark.django_db
def test_upload_rejects_oversized_image(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    big_file = SimpleUploadedFile(
        "pic.png", b"0" * (11 * 1024 * 1024), content_type="image/png"
    )

    response = client.post("/api/broadcast-media/", {"file": big_file}, format="multipart")

    assert response.status_code == 400
    assert "10" in str(response.data)


@pytest.mark.django_db
def test_seller_cannot_upload_broadcast_media(api_client_for, make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)
    client = api_client_for(seller)

    response = client.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admin_cannot_fetch_another_tenants_media_file(
    api_client_for, make_user, make_tenant
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    admin_b = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)
    client_b = api_client_for(admin_b)
    upload = client_b.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")
    media_id = upload.data["id"]

    client_a = api_client_for(admin_a)
    response = client_a.get(f"/api/broadcast-media/{media_id}/file/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_tenant_admin_can_fetch_their_own_media_file(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    upload = client.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")
    media_id = upload.data["id"]

    response = client.get(f"/api/broadcast-media/{media_id}/file/")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


@pytest.mark.django_db
def test_tenant_admin_cannot_attach_another_tenants_media_to_a_broadcast(
    api_client_for, make_user, make_tenant
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    admin_b = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)
    client_b = api_client_for(admin_b)
    upload = client_b.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")
    media_id = upload.data["id"]

    client_a = api_client_for(admin_a)
    response = client_a.post(
        "/api/broadcasts/",
        {"title": "Sale", "body": "hi", "media_id": media_id},
        format="json",
    )

    assert response.status_code == 400
    assert "media_id" in response.data


@pytest.mark.django_db
def test_tenant_admin_only_sees_their_own_media_in_the_list(
    api_client_for, make_user, make_tenant
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    admin_b = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)
    api_client_for(admin_a).post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")
    api_client_for(admin_b).post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")

    response = api_client_for(admin_a).get("/api/broadcast-media/")

    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
