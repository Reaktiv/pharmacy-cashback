import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.django_db
def test_seller_can_view_their_profile_page(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.get("/seller/profile/")

    assert response.status_code == 200
    assert seller.full_name.encode() in response.content


@pytest.mark.django_db
def test_seller_can_update_name_and_phone(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/profile/", {"full_name": "Yangi Ism", "phone": "+998901112233"}
    )

    assert response.status_code == 302
    seller.refresh_from_db()
    assert seller.full_name == "Yangi Ism"
    assert seller.phone == "+998901112233"
    seller.user.profile.refresh_from_db()
    assert seller.user.profile.full_name == "Yangi Ism"


@pytest.mark.django_db
def test_seller_avatar_upload_and_fetch_round_trip(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    avatar = SimpleUploadedFile("avatar.png", TINY_PNG_BYTES, content_type="image/png")
    response = client.post(
        "/seller/profile/",
        {"full_name": seller.full_name, "phone": seller.phone, "avatar": avatar},
    )
    assert response.status_code == 302

    fetched = client.get("/seller/profile/avatar/")
    assert fetched.status_code == 200


@pytest.mark.django_db
def test_seller_can_change_own_password(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/profile/change-password/",
        {
            "old_password": "pass1234",
            "new_password1": "a-much-str0nger-pass",
            "new_password2": "a-much-str0nger-pass",
        },
    )

    assert response.status_code == 302
    seller.user.refresh_from_db()
    assert seller.user.check_password("a-much-str0nger-pass")

    # Session auth hash must be refreshed, or the seller is logged out by
    # their own password change mid-session.
    still_authenticated = client.get("/seller/")
    assert still_authenticated.status_code == 200


@pytest.mark.django_db
def test_change_password_rejects_wrong_old_password(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/profile/change-password/",
        {
            "old_password": "wrong-password",
            "new_password1": "a-much-str0nger-pass",
            "new_password2": "a-much-str0nger-pass",
        },
    )

    assert response.status_code == 302
    seller.user.refresh_from_db()
    assert seller.user.check_password("pass1234")


@pytest.mark.django_db
def test_change_password_rejects_mismatched_confirmation(
    client, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/profile/change-password/",
        {
            "old_password": "pass1234",
            "new_password1": "a-much-str0nger-pass",
            "new_password2": "a-different-pass",
        },
    )

    assert response.status_code == 302
    seller.user.refresh_from_db()
    assert seller.user.check_password("pass1234")


@pytest.mark.django_db
def test_seller_can_fetch_tenant_logo_once_tenant_admin_uploads_one(
    client, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    logo = SimpleUploadedFile("logo.png", TINY_PNG_BYTES, content_type="image/png")
    tenant.logo = logo
    tenant.save(update_fields=["logo"])
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.get("/seller/tenant-logo/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_seller_tenant_logo_404s_when_tenant_has_no_logo(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    assert client.get("/seller/tenant-logo/").status_code == 404


@pytest.mark.django_db
def test_non_seller_role_gets_forbidden_on_profile_page(client, make_tenant, make_user):
    from apps.accounts.models import UserProfile

    tenant = make_tenant("t")
    make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant, username="admin1")
    client.login(username="admin1", password="pass1234")

    response = client.get("/seller/profile/")

    assert response.status_code == 403
