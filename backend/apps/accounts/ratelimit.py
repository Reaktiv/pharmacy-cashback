"""Dependency-free fixed-window rate limiter backed by the cache (same
Redis instance as apps.tenants.models.GlobalSettings).

DRF's own throttling classes (rest_framework.throttling) cover DRF views —
see TenantAwareTokenObtainPairView. This exists for the plain Django views
DRF throttling never reaches: SellerLoginView (session-based) and the
seller-web OTP-redeem endpoint (apps.ledger.services.redeem_via_otp) — both
predate/bypass DRF, so nothing else limits attempts against them.
"""

from django.core.cache import cache


class RateLimitExceededError(Exception):
    """Raised by check_rate_limit() once a key has hit its cap for the
    current window."""


def check_rate_limit(*, key: str, limit: int, window_seconds: int) -> None:
    """Raises RateLimitExceededError once `key` has been hit more than
    `limit` times within `window_seconds` of its first hit. cache.add()
    only succeeds for the first caller in a window (atomic in the cache
    backend), so this is race-safe under concurrent requests.

    Counts every call, success or failure — right for login (every attempt,
    right or wrong password, should count). For actions where a legitimate
    high-volume caller can rack up many *successful* calls (e.g. a busy
    seller redeeming many valid OTPs in a row), pair peek_rate_limit() below
    with record_failed_attempt() instead, so only failures count.
    """
    if cache.add(key, 1, timeout=window_seconds):
        return
    if cache.incr(key) > limit:
        raise RateLimitExceededError(
            "Juda ko'p urinish qilindi. Iltimos, birozdan so'ng qayta urinib ko'ring."
        )


def reserve_rate_limit_slot(*, key: str, limit: int, window_seconds: int) -> None:
    """Same body as check_rate_limit() — the reservation *is* the atomic
    increment, raising once it pushes `key` over `limit`. Use this (paired
    with release_rate_limit_slot() below) instead of check_rate_limit()
    itself when only *failed* attempts should count: reserving up front and
    releasing on success gets the same "only failures count" behavior as
    the old peek_rate_limit()/record_failed_attempt() pair did, but without
    that pair's race — peek_rate_limit's plain `cache.get()` read let N
    concurrent requests all observe the same pre-increment count and all
    pass, even once N exceeded the limit (audit finding M-1). Reserving via
    an atomic increment closes that: there is no window where two
    concurrent callers can both read a stale count, because there's nothing
    to read — the increment itself is the check.
    """
    if cache.add(key, 1, timeout=window_seconds):
        return
    if cache.incr(key) > limit:
        raise RateLimitExceededError(
            "Juda ko'p urinish qilindi. Iltimos, birozdan so'ng qayta urinib ko'ring."
        )


def release_rate_limit_slot(*, key: str) -> None:
    """Undoes reserve_rate_limit_slot()'s increment once the guarded
    attempt actually succeeded — call this only on success, the mirror
    image of the old record_failed_attempt()'s "call only on failure"."""
    try:
        cache.decr(key)
    except ValueError:
        # Key already expired/evicted (its window rolled over) between the
        # reservation and now — nothing to release, and decrementing a
        # nonexistent key would just fabricate a bogus negative counter.
        pass


def client_identity(request) -> str:
    """The real client IP, trusting only headers nginx itself sets from the
    actual TCP connection — never a client-supplied one.

    X-Forwarded-For is NOT used here: nginx's `proxy_set_header
    X-Forwarded-For $proxy_add_x_forwarded_for` (nginx/app.conf) *appends*
    to whatever X-Forwarded-For the client already sent rather than
    replacing it, so a client could set a fresh bogus value on every
    request and get a brand new rate-limit bucket each time — a full
    bypass of every limiter keyed by this function (audit finding C-1).

    X-Real-IP is safe to trust instead: nginx's `proxy_set_header
    X-Real-IP $remote_addr` unconditionally *replaces* any X-Real-IP the
    client sent with nginx's own view of the TCP peer address, and nginx
    is the only thing that can reach the app (ufw exposes 80/443 only;
    Postgres/Redis/the app port are never published — see DEPLOY.md). A
    request that reaches Django with an X-Real-IP header can only have
    gotten it from nginx.

    REMOTE_ADDR is the fallback for anything that isn't behind nginx: the
    local dev server, the Django test client, and manage.py runserver.
    """
    real_ip = request.META.get("HTTP_X_REAL_IP")
    return real_ip or request.META.get("REMOTE_ADDR") or "unknown"
