import pytest

from apps.accounts.ratelimit import (
    RateLimitExceededError,
    check_rate_limit,
    client_identity,
    peek_rate_limit,
    record_failed_attempt,
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


def test_peek_rate_limit_allows_a_key_that_was_never_recorded():
    peek_rate_limit(key="test:peek-fresh", limit=3)  # must not raise


def test_peek_rate_limit_does_not_increment():
    for _ in range(5):
        peek_rate_limit(key="test:peek-noop", limit=1)  # must never raise, never increments


def test_peek_rate_limit_raises_once_recorded_failures_reach_the_limit():
    for _ in range(3):
        record_failed_attempt(key="test:peek-blocks", window_seconds=60)

    with pytest.raises(RateLimitExceededError):
        peek_rate_limit(key="test:peek-blocks", limit=3)


def test_peek_rate_limit_allows_under_the_limit():
    for _ in range(2):
        record_failed_attempt(key="test:peek-under", window_seconds=60)

    peek_rate_limit(key="test:peek-under", limit=3)  # 2 failures recorded, must not raise


def test_successful_calls_that_never_record_a_failure_never_trip_the_limit():
    """The whole point of splitting check_rate_limit into peek/record: a
    caller that only ever calls peek_rate_limit (i.e. every attempt
    succeeds) must never get blocked, no matter how many times it's
    called."""
    for _ in range(50):
        peek_rate_limit(key="test:always-succeeds", limit=3)  # must never raise


class _FakeRequest:
    def __init__(self, meta):
        self.META = meta


def test_client_identity_prefers_x_forwarded_for():
    request = _FakeRequest({"HTTP_X_FORWARDED_FOR": "1.2.3.4", "REMOTE_ADDR": "10.0.0.1"})
    assert client_identity(request) == "1.2.3.4"


def test_client_identity_falls_back_to_remote_addr():
    request = _FakeRequest({"REMOTE_ADDR": "10.0.0.1"})
    assert client_identity(request) == "10.0.0.1"
