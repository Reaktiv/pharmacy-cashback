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


def peek_rate_limit(*, key: str, limit: int) -> None:
    """Raises RateLimitExceededError if `key` is already at/over `limit`,
    without incrementing anything — call this up front so a request that's
    going to be rejected doesn't do any work first. Pairs with
    record_failed_attempt(), which does the actual incrementing."""
    count = cache.get(key)
    if count is not None and count >= limit:
        raise RateLimitExceededError(
            "Juda ko'p urinish qilindi. Iltimos, birozdan so'ng qayta urinib ko'ring."
        )


def record_failed_attempt(*, key: str, window_seconds: int) -> None:
    """Increments `key`'s failure count, starting a fresh `window_seconds`
    TTL on the first failure. Call only when an attempt actually failed —
    pairs with peek_rate_limit(), which does the actual rejecting."""
    if not cache.add(key, 1, timeout=window_seconds):
        cache.incr(key)


def client_identity(request) -> str:
    """Same identification convention as DRF's SimpleRateThrottle.get_ident
    with NUM_PROXIES unset (this project's REST_FRAMEWORK setting doesn't
    configure it either): the whole X-Forwarded-For header if nginx set
    one (see nginx/app.conf's proxy_set_header), else REMOTE_ADDR. Keys the
    plain-Django rate limits below the same way DRF throttles key JWT
    login, so both mechanisms treat "the client" identically."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    remote_addr = request.META.get("REMOTE_ADDR")
    return "".join(xff.split()) if xff else remote_addr
