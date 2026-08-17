import threading

import pytest

from apps.accounts.ratelimit import (
    RateLimitExceededError,
    check_rate_limit,
    client_identity,
    release_rate_limit_slot,
    reserve_rate_limit_slot,
)


def test_check_rate_limit_allows_up_to_the_limit():
    for _ in range(3):
        check_rate_limit(key="test:allow", limit=3, window_seconds=60)  # must not raise


def test_check_rate_limit_raises_once_the_limit_is_exceeded():
    for _ in range(3):
        check_rate_limit(key="test:exceed", limit=3, window_seconds=60)

    with pytest.raises(RateLimitExceededError):
        check_rate_limit(key="test:exceed", limit=3, window_seconds=60)


def test_check_rate_limit_keys_are_independent():
    for _ in range(3):
        check_rate_limit(key="test:a", limit=3, window_seconds=60)

    check_rate_limit(key="test:b", limit=3, window_seconds=60)  # a fresh key, must not raise


def test_reserve_rate_limit_slot_allows_a_fresh_key():
    reserve_rate_limit_slot(key="test:reserve-fresh", limit=3, window_seconds=60)  # must not raise


def test_reserve_then_release_never_accumulates():
    """A caller that reserves and immediately releases every time (i.e.
    every attempt succeeds) must never get blocked, no matter how many
    times it's called — same "only failures count" guarantee the old
    peek/record pair gave, now via an atomic reserve/release pair."""
    for _ in range(50):
        reserve_rate_limit_slot(key="test:always-succeeds", limit=3, window_seconds=60)
        release_rate_limit_slot(key="test:always-succeeds")  # must never raise


def test_reserve_rate_limit_slot_raises_once_unreleased_reservations_reach_the_limit():
    for _ in range(3):
        reserve_rate_limit_slot(key="test:reserve-blocks", limit=3, window_seconds=60)

    with pytest.raises(RateLimitExceededError):
        reserve_rate_limit_slot(key="test:reserve-blocks", limit=3, window_seconds=60)


def test_reserve_rate_limit_slot_allows_under_the_limit():
    for _ in range(2):
        reserve_rate_limit_slot(key="test:reserve-under", limit=3, window_seconds=60)

    reserve_rate_limit_slot(key="test:reserve-under", limit=3, window_seconds=60)  # 3rd, still ok


def test_release_rate_limit_slot_on_an_expired_or_missing_key_does_not_raise():
    release_rate_limit_slot(key="test:never-reserved")  # must not raise


def test_reserve_rate_limit_slot_is_race_safe_under_concurrent_requests():
    """Direct regression test for audit finding M-1: N threads all calling
    reserve_rate_limit_slot() concurrently, with the limit set to N-1, must
    let through no more than N-1 of them — the old peek-then-record pattern
    could let all N through if they all read the shared counter before any
    of them wrote to it. Uses real threads (not asyncio) against the actual
    cache backend so the race condition, if reintroduced, would actually
    manifest rather than being hidden by single-threaded test execution.
    """
    key = "test:concurrent-reserve"
    limit = 19
    thread_count = 20
    results: list[bool] = []
    results_lock = threading.Lock()
    start_barrier = threading.Barrier(thread_count)

    def attempt():
        start_barrier.wait()  # maximize actual overlap between threads
        try:
            reserve_rate_limit_slot(key=key, limit=limit, window_seconds=60)
            allowed = True
        except RateLimitExceededError:
            allowed = False
        with results_lock:
            results.append(allowed)

    threads = [threading.Thread(target=attempt) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == limit
    assert results.count(False) == thread_count - limit


class _FakeRequest:
    def __init__(self, meta):
        self.META = meta


def test_client_identity_ignores_x_forwarded_for():
    """X-Forwarded-For must never be trusted: nginx appends to it rather
    than replacing it (nginx/app.conf), so a client-supplied value here is
    exactly the audit C-1 bypass — a fresh header per request would mint a
    fresh rate-limit bucket every time. REMOTE_ADDR must be used instead
    when there's no X-Real-IP."""
    request = _FakeRequest({"HTTP_X_FORWARDED_FOR": "1.2.3.4", "REMOTE_ADDR": "10.0.0.1"})
    assert client_identity(request) == "10.0.0.1"


def test_client_identity_prefers_x_real_ip_over_remote_addr():
    """X-Real-IP is trustworthy: nginx's proxy_set_header replaces (not
    appends) it with nginx's own view of the TCP peer, so it can be used
    even when REMOTE_ADDR is just nginx's own container IP."""
    request = _FakeRequest({"HTTP_X_REAL_IP": "203.0.113.9", "REMOTE_ADDR": "172.18.0.5"})
    assert client_identity(request) == "203.0.113.9"


def test_client_identity_falls_back_to_remote_addr():
    request = _FakeRequest({"REMOTE_ADDR": "10.0.0.1"})
    assert client_identity(request) == "10.0.0.1"


def test_client_identity_spoofed_x_forwarded_for_cannot_mint_a_fresh_bucket():
    """Direct regression test for C-1: changing X-Forwarded-For on every
    request must NOT change the rate-limit identity when the real
    connection (REMOTE_ADDR / X-Real-IP) stays the same."""
    identities = {
        client_identity(_FakeRequest({"HTTP_X_FORWARDED_FOR": xff, "REMOTE_ADDR": "10.0.0.1"}))
        for xff in ["1.1.1.1", "2.2.2.2", "attacker-controlled-garbage", ""]
    }
    assert identities == {"10.0.0.1"}
