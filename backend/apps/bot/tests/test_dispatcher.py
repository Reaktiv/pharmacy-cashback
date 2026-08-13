import asyncio

import pytest

from apps.bot.dispatcher import _dispatcher_cache, build_dispatcher


@pytest.fixture(autouse=True)
def _clear_dispatcher_cache():
    """The cache is a module-level singleton (by design — see
    dispatcher.py), so it must not leak a Dispatcher built by one test into
    the next."""
    _dispatcher_cache.clear()
    yield
    _dispatcher_cache.clear()


def test_build_dispatcher_reuses_the_same_instance_within_one_loop():
    async def _two_calls_same_loop():
        return build_dispatcher(), build_dispatcher()

    first, second = asyncio.run(_two_calls_same_loop())

    assert first is second


def test_build_dispatcher_builds_a_fresh_instance_for_a_different_loop():
    async def _one_call():
        return build_dispatcher()

    # Each asyncio.run() spins up (and tears down) its own event loop, so
    # this is exactly the "loop changed" case build_dispatcher must detect.
    first = asyncio.run(_one_call())
    second = asyncio.run(_one_call())

    assert first is not second


def test_build_dispatcher_cache_never_grows_beyond_one_entry():
    """Switching loops must evict the old entry, not accumulate one per
    loop forever — otherwise dev/runserver traffic (where the loop can
    differ per request) would leak a Dispatcher/Redis connection per
    request instead of just per switch."""

    async def _one_call():
        build_dispatcher()

    for _ in range(3):
        asyncio.run(_one_call())

    assert len(_dispatcher_cache) == 1
