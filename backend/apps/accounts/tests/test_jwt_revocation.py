"""Regression tests for audit finding H-3: before this, nothing could ever
revoke a JWT before its own expiry (up to 24h for a refresh token) — not a
password change, not an explicit logout. These tests reproduce both halves
of the original gap and prove each is now closed:

  1. Logging out must actually kill the session (blacklist the refresh
     token), not just forget it client-side.
  2. Changing a password must immediately invalidate every access token
     issued under the old password, not just future logins.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile


@pytest.mark.django_db
def test_logout_blacklists_the_refresh_token(make_user):
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    login = client.post(
        "/api/auth/token/", {"username": "admin1", "password": "pass1234"}, format="json"
    )
    assert login.status_code == 200
    access, refresh = login.data["access"], login.data["refresh"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    logout = client.post("/api/auth/token/logout/", {"refresh": refresh}, format="json")
    assert logout.status_code == 204

    # The exact original failure mode: before H-3, this refresh token would
    # still work here, minutes or hours after "logout".
    refresh_attempt = client.post(
        "/api/auth/token/refresh/", {"refresh": refresh}, format="json"
    )
    assert refresh_attempt.status_code == 401


@pytest.mark.django_db
def test_logout_requires_authentication(make_user):
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    response = client.post("/api/auth/token/logout/", {"refresh": "whatever"}, format="json")

    assert response.status_code == 401


@pytest.mark.django_db
def test_logout_with_an_already_expired_or_garbage_refresh_token_still_succeeds(make_user):
    """A logout button click must never fail just because the token was
    already dead by the time it arrived — the end state (unusable) is the
    same either way."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()
    login = client.post(
        "/api/auth/token/", {"username": "admin1", "password": "pass1234"}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    response = client.post(
        "/api/auth/token/logout/", {"refresh": "not-a-real-token"}, format="json"
    )

    assert response.status_code == 204


@pytest.mark.django_db
def test_changing_password_invalidates_previously_issued_access_tokens(make_user):
    """The core CHECK_REVOKE_TOKEN behavior: an access token minted under
    the old password must stop working the instant the password changes —
    not linger until its own 30-minute expiry, and not require the
    attacker to also somehow learn the new password."""
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()
    login = client.post(
        "/api/auth/token/", {"username": "admin1", "password": "pass1234"}, format="json"
    )
    old_access = login.data["access"]

    still_works = APIClient()
    still_works.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
    assert still_works.get("/api/me/").status_code == 200

    admin.set_password("a-brand-new-password")
    admin.save()

    stolen_session = APIClient()
    stolen_session.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
    response = stolen_session.get("/api/me/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_a_fresh_login_after_a_password_change_works_normally(make_user):
    """The revocation check must not become permanently stuck rejecting
    this user — a new token minted under the new password must authenticate
    normally."""
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    admin.set_password("a-brand-new-password")
    admin.save()
    client = APIClient()

    login = client.post(
        "/api/auth/token/",
        {"username": "admin1", "password": "a-brand-new-password"},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    response = client.get("/api/me/")

    assert response.status_code == 200
