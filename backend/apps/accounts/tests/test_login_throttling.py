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
def test_jwt_login_is_rate_limited_after_repeated_attempts(make_user):
    """TenantAwareTokenObtainPairView is a DRF view — LoginRateThrottle
    (apps.accounts.views) should reject further attempts with 429 once the
    limit is hit, independent of whether the credentials are right."""
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
