import pytest
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.accounts.views import SELLER_LOGIN_ATTEMPT_LIMIT


@pytest.mark.django_db
def test_seller_web_login_is_rate_limited_after_repeated_attempts(client, make_user):
    """SellerLoginView is a plain Django view (session auth), so DRF's
    throttle classes never reach it — this exercises the custom limiter in
    apps.accounts.ratelimit instead."""
    make_user(username="seller1")

    for _ in range(SELLER_LOGIN_ATTEMPT_LIMIT):
        client.post("/accounts/login/", {"username": "seller1", "password": "wrong"})

    response = client.post("/accounts/login/", {"username": "seller1", "password": "wrong"})

    assert response.status_code == 200
    assert b"urinish qilindi" in response.content


@pytest.mark.django_db
def test_seller_web_login_still_works_under_the_limit(client, make_user):
    make_user(username="seller1")

    response = client.post("/accounts/login/", {"username": "seller1", "password": "pass1234"})

    assert response.status_code == 302


@pytest.mark.django_db
def test_jwt_login_is_rate_limited_after_repeated_wrong_attempts(make_user):
    """TenantAwareTokenObtainPairView.post() (apps.accounts.views) only
    counts *failed* attempts against ADMIN_LOGIN_ATTEMPT_LIMIT — this
    exercises that a run of wrong passwords still gets capped."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    for _ in range(5):
        client.post(
            "/api/auth/token/", {"username": "admin1", "password": "wrong"}, format="json"
        )

    response = client.post(
        "/api/auth/token/", {"username": "admin1", "password": "wrong"}, format="json"
    )

    assert response.status_code == 429


@pytest.mark.django_db
def test_jwt_login_is_not_throttled_by_repeated_correct_attempts(make_user):
    """The bug this replaced DRF's AnonRateThrottle for: a real admin
    logging in correctly several times in a row (multiple tabs/devices)
    got locked out for minutes despite never once getting it wrong, because
    the old throttle counted every request, not just failures."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    for _ in range(8):
        response = client.post(
            "/api/auth/token/", {"username": "admin1", "password": "pass1234"}, format="json"
        )
        assert response.status_code == 200


@pytest.mark.django_db
def test_jwt_login_throttle_clears_after_a_correct_login(make_user):
    """A wrong attempt followed by the right password shouldn't leave the
    counter primed to reject a *subsequent* wrong guess as if it were the
    5th — record_failed_attempt() only fires from the except branch, so a
    success in between never resets or touches the counter either way;
    this just confirms the two kinds of attempt don't interfere."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    client.post("/api/auth/token/", {"username": "admin1", "password": "wrong"}, format="json")
    response = client.post(
        "/api/auth/token/", {"username": "admin1", "password": "pass1234"}, format="json"
    )

    assert response.status_code == 200
