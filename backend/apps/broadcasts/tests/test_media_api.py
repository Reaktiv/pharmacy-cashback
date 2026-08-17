import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import UserProfile
from apps.broadcasts.models import BroadcastMedia


def _tiny_png():
    """A genuinely decodable PNG, not just the magic-byte header — the
    upload endpoint now verifies the image actually decodes (audit finding
    H-1: the old check trusted the client-declared Content-Type alone), so
    a fixture that's only a signature followed by junk bytes would
    (correctly) be rejected."""
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buf, format="PNG")
    return SimpleUploadedFile("pic.png", buf.getvalue(), content_type="image/png")


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
def test_upload_with_a_path_traversal_filename_stays_inside_the_tenant_directory(
    api_client_for, make_user, make_tenant
):
    """Pre-production gate review: broadcast_media_upload_path() (models.py)
    builds the stored path from a random UUID plus only os.path.splitext()'s
    extension of the client-supplied filename — never the filename itself.
    Confirms an adversarial filename can't escape apps/broadcasts/<tenant_id>/
    the way it could if the raw filename were ever used directly."""
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buf, format="PNG")
    traversal_file = SimpleUploadedFile(
        "../../../../etc/cron.d/evil.png", buf.getvalue(), content_type="image/png"
    )

    response = client.post("/api/broadcast-media/", {"file": traversal_file}, format="multipart")

    assert response.status_code == 201, response.data
    media = BroadcastMedia.objects.all_tenants().get(pk=response.data["id"])
    assert media.file.name.startswith(f"broadcast_media/{tenant.id}/")
    assert ".." not in media.file.name
    assert media.file.name.endswith(".png")


@pytest.mark.django_db
def test_upload_rejects_svg_disguised_as_an_image(api_client_for, make_user, make_tenant):
    """Regression test for audit finding H-1: an SVG (which can carry a
    <script> tag) with a client-declared image/* Content-Type used to pass
    every check that existed before this fix, and would then be served
    back inline with that same declared type — a stored-XSS path. The
    upload must now be rejected: image/svg+xml isn't in the allowlist, and
    even if it somehow were, Pillow can't decode it."""
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    evil_svg = SimpleUploadedFile(
        "evil.svg",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(document.cookie)</script></svg>",
        content_type="image/svg+xml",
    )

    response = client.post("/api/broadcast-media/", {"file": evil_svg}, format="multipart")

    assert response.status_code == 400
    assert "rasm yoki video" in str(response.data).lower()


@pytest.mark.django_db
def test_upload_rejects_a_file_whose_declared_type_does_not_match_its_bytes(
    api_client_for, make_user, make_tenant
):
    """A file claiming Content-Type: image/png but containing bytes that
    aren't actually a decodable image must be rejected, not just checked by
    string-matching the declared type (the exact gap audit finding H-1
    describes)."""
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    fake_image = SimpleUploadedFile(
        "not-a-real-image.png", b"this is not image data at all", content_type="image/png"
    )

    response = client.post("/api/broadcast-media/", {"file": fake_image}, format="multipart")

    assert response.status_code == 400
    assert "haqiqiy rasm emas" in str(response.data).lower()


@pytest.mark.django_db
def test_upload_rejects_a_file_whose_declared_type_claims_video_but_is_not(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    fake_video = SimpleUploadedFile(
        "not-a-real-video.mp4", b"this is not video data at all", content_type="video/mp4"
    )

    response = client.post("/api/broadcast-media/", {"file": fake_video}, format="multipart")

    assert response.status_code == 400
    assert "haqiqiy video emas" in str(response.data).lower()


@pytest.mark.django_db
def test_upload_accepts_a_real_mp4_container(api_client_for, make_user, make_tenant):
    """A genuine (if minimal) MP4 container — real 'ftyp' box signature —
    must still be accepted; the fix must not reject legitimate videos."""
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    # A minimal, real ISO base media 'ftyp' box (MP4 signature) followed by
    # padding — enough for the container-signature check without needing a
    # full, playable video file.
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"0" * 100
    real_video = SimpleUploadedFile("clip.mp4", mp4_bytes, content_type="video/mp4")

    response = client.post("/api/broadcast-media/", {"file": real_video}, format="multipart")

    assert response.status_code == 201, response.data
    assert response.data["media_type"] == "video"


@pytest.mark.django_db
def test_file_action_hands_off_to_nginx_via_x_accel_redirect(
    api_client_for, make_user, make_tenant
):
    """The app process must not stream the bytes itself — it should return
    an empty body and let X-Accel-Redirect point nginx at the real file
    (nginx/app.conf's internal /internal-media/ location). The tenant-scope
    check happens in get_object() before this header is ever set, same as
    before."""
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    upload = client.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")
    media_id = upload.data["id"]
    media = BroadcastMedia.objects.all_tenants().get(pk=media_id)

    response = client.get(f"/api/broadcast-media/{media_id}/file/")

    assert response.status_code == 200
    assert response["X-Accel-Redirect"] == f"/internal-media/{media.file.name}"
    assert response.content == b""
    assert response["Content-Type"] == "image/png"
    assert 'filename="pic.png"' in response["Content-Disposition"]


@pytest.mark.django_db
def test_media_file_is_served_as_an_attachment_not_inline(api_client_for, make_user, make_tenant):
    """Second layer of the H-1 fix: even for an upload that passes
    validation, the response must force a download (Content-Disposition:
    attachment) rather than let a browser render it inline in this app's
    origin if someone navigates to the URL directly. The admin panel itself
    is unaffected — it always fetches this URL via apiFetchObjectUrl
    (fetch + Blob), where Content-Disposition has no bearing on rendering."""
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)
    upload = client.post("/api/broadcast-media/", {"file": _tiny_png()}, format="multipart")
    media_id = upload.data["id"]

    response = client.get(f"/api/broadcast-media/{media_id}/file/")

    assert response["Content-Disposition"].startswith("attachment")


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
