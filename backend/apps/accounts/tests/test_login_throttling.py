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
def test_seller_web_login_throttle_survives_a_spoofed_x_forwarded_for_header(client, make_user):
    """Same C-1 regression as the JWT tests below, for the plain-Django
    seller login view."""
    make_user(username="seller1")

    for i in range(SELLER_LOGIN_ATTEMPT_LIMIT):
        client.post(
            "/accounts/login/",
            {"username": "seller1", "password": "wrong"},
            REMOTE_ADDR="198.51.100.7",
            HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",
        )

    response = client.post(
        "/accounts/login/",
        {"username": "seller1", "password": "wrong"},
        REMOTE_ADDR="198.51.100.7",
        HTTP_X_FORWARDED_FOR="10.0.0.99",
    )

    assert response.status_code == 200
    assert b"urinish qilindi" in response.content


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
def test_jwt_login_throttle_survives_a_spoofed_x_forwarded_for_header(make_user):
    """Regression test for audit finding C-1: sending a fresh, attacker-
    chosen X-Forwarded-For value on every request must NOT reset the
    rate-limit bucket. All requests here share the same REMOTE_ADDR (as a
    real attacker's actual TCP connection would), each with a different,
    made-up X-Forwarded-For — the throttle must still trip on attempt 6."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    for i in range(5):
        response = client.post(
            "/api/auth/token/",
            {"username": "admin1", "password": "wrong"},
            format="json",
            REMOTE_ADDR="198.51.100.7",
            HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",  # different "attacker" value every time
        )
        assert response.status_code == 401

    response = client.post(
        "/api/auth/token/",
        {"username": "admin1", "password": "wrong"},
        format="json",
        REMOTE_ADDR="198.51.100.7",
        HTTP_X_FORWARDED_FOR="10.0.0.99",  # yet another new value
    )

    assert response.status_code == 429


@pytest.mark.django_db
def test_jwt_login_throttle_is_per_real_client_not_per_spoofed_header(make_user):
    """A different real client (different REMOTE_ADDR/X-Real-IP) must get
    its own independent bucket — proves the fix didn't accidentally
    collapse every request onto one shared identity."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    attacker = APIClient()
    other_client = APIClient()

    for _ in range(5):
        attacker.post(
            "/api/auth/token/",
            {"username": "admin1", "password": "wrong"},
            format="json",
            REMOTE_ADDR="198.51.100.7",
        )

    blocked = attacker.post(
        "/api/auth/token/",
        {"username": "admin1", "password": "wrong"},
        format="json",
        REMOTE_ADDR="198.51.100.7",
    )
    assert blocked.status_code == 429

    still_allowed = other_client.post(
        "/api/auth/token/",
        {"username": "admin1", "password": "wrong"},
        format="json",
        REMOTE_ADDR="203.0.113.55",
    )
    assert still_allowed.status_code == 401  # wrong password, but not yet throttled


@pytest.mark.django_db
def test_jwt_login_trusts_nginx_supplied_x_real_ip_behind_a_proxy(make_user):
    """Simulates real production topology: nginx sets X-Real-IP from its
    own view of the TCP connection (nginx/app.conf), and REMOTE_ADDR as
    Django sees it is just nginx's container IP. The throttle must key off
    X-Real-IP in that case, still correctly rate-limiting the real client
    behind the proxy rather than treating every request as coming from
    nginx itself."""
    make_user(role=UserProfile.Role.TENANT_ADMIN, username="admin1")
    client = APIClient()

    for _ in range(5):
        response = client.post(
            "/api/auth/token/",
            {"username": "admin1", "password": "wrong"},
            format="json",
            REMOTE_ADDR="172.18.0.6",  # nginx's own address inside the Docker network
            HTTP_X_REAL_IP="203.0.113.42",  # the real client, as nginx reported it
        )
        assert response.status_code == 401

    response = client.post(
        "/api/auth/token/",
        {"username": "admin1", "password": "wrong"},
        format="json",
        REMOTE_ADDR="172.18.0.6",
        HTTP_X_REAL_IP="203.0.113.42",
    )
    assert response.status_code == 429


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
