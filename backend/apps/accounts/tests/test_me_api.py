import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import UserProfile

# A valid, minimal 1x1 transparent PNG.
TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.django_db
def test_any_role_can_read_their_own_profile(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.get("/api/me/")

    assert response.status_code == 200
    assert response.data["username"] == admin.username
    assert response.data["role"] == UserProfile.Role.TENANT_ADMIN
    assert response.data["tenant_name"] == tenant.name
    assert response.data["has_avatar"] is False


@pytest.mark.django_db
def test_anonymous_request_is_rejected(client):
    response = client.get("/api/me/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_can_update_own_name_and_phone(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant)
    client = api_client_for(manager)

    response = client.patch(
        "/api/me/", {"full_name": "Aziz Karimov", "phone": "+998901234567"}
    )

    assert response.status_code == 200
    manager.profile.refresh_from_db()
    assert manager.profile.full_name == "Aziz Karimov"
    assert manager.profile.phone == "+998901234567"


@pytest.mark.django_db
def test_can_update_own_language(api_client_for, make_user, make_tenant):
    """UserProfile.language is the single source of truth shared with the
    seller-web till pages (apps.seller_web.i18n.get_language) — this is
    what the React profile drawer's language switcher writes."""
    tenant = make_tenant("t")
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant)
    client = api_client_for(manager)

    response = client.patch("/api/me/", {"language": "ru"})

    assert response.status_code == 200
    manager.profile.refresh_from_db()
    assert manager.profile.language == "ru"


@pytest.mark.django_db
def test_updating_own_language_rejects_unsupported_code(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant)
    client = api_client_for(manager)

    response = client.patch("/api/me/", {"language": "fr"})

    assert response.status_code == 400
    manager.profile.refresh_from_db()
    assert manager.profile.language == "uz"


@pytest.mark.django_db
def test_seller_editing_own_profile_updates_the_linked_seller_row_too(
    api_client_for, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client = api_client_for(seller.user)

    response = client.patch(
        "/api/me/", {"full_name": "Yangi Ism", "phone": "+998901112233"}
    )

    assert response.status_code == 200
    seller.refresh_from_db()
    assert seller.full_name == "Yangi Ism"
    assert seller.phone == "+998901112233"


@pytest.mark.django_db
def test_seller_edited_via_admin_flow_mirrors_into_their_profile(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    seller.full_name = "Renamed By Manager"
    seller.save()

    seller.user.profile.refresh_from_db()
    assert seller.user.profile.full_name == "Renamed By Manager"


@pytest.mark.django_db
def test_avatar_upload_and_fetch_round_trip(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    tiny_png = SimpleUploadedFile("avatar.png", TINY_PNG_BYTES, content_type="image/png")
    upload = client.patch("/api/me/", {"avatar": tiny_png}, format="multipart")
    assert upload.status_code == 200
    assert upload.data["has_avatar"] is True

    fetched = client.get("/api/me/avatar/")
    assert fetched.status_code == 200

    remove = client.patch("/api/me/", {"remove_avatar": "true"}, format="multipart")
    assert remove.status_code == 200
    assert remove.data["has_avatar"] is False
    assert client.get("/api/me/avatar/").status_code == 404


@pytest.mark.django_db
def test_avatar_rejects_non_image_file(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    text_file = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")
    response = client.patch("/api/me/", {"avatar": text_file}, format="multipart")

    assert response.status_code == 400


@pytest.mark.django_db
def test_can_change_own_password(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/me/change-password/",
        {"old_password": "pass1234", "new_password": "a-much-str0nger-pass"},
    )

    assert response.status_code == 204
    admin.refresh_from_db()
    assert admin.check_password("a-much-str0nger-pass")


@pytest.mark.django_db
def test_change_password_rejects_wrong_old_password(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/me/change-password/",
        {"old_password": "wrong-password", "new_password": "a-much-str0nger-pass"},
    )

    assert response.status_code == 400
    admin.refresh_from_db()
    assert admin.check_password("pass1234")


@pytest.mark.django_db
def test_change_password_rejects_weak_new_password(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/me/change-password/",
        {"old_password": "pass1234", "new_password": "12345"},
    )

    assert response.status_code == 400
    admin.refresh_from_db()
    assert admin.check_password("pass1234")
