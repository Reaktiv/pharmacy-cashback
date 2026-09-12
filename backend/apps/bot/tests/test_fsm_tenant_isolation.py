"""Audit finding C-1: FSM state must be isolated per tenant bot.

This is a multibot process — one Dispatcher, one Redis, many tenant bots
(apps/bot/dispatcher.py) — so the ONLY thing separating one pharmacy's
conversation state from another's is the bot id inside the storage key.
aiogram's DefaultKeyBuilder omits it unless asked (`with_bot_id=False`),
which is exactly the bug these tests pin down.

The first three tests are pure key-derivation and need no services at all.
The last two drive the real RedisStorage against the real Redis the rest of
the suite already requires (conftest.py's _clear_cache fixture uses it), so
they cover the storage round trip and not just the string building.
"""

import asyncio

import pytest
from aiogram.fsm.storage.base import StorageKey
from django.conf import settings

from apps.bot.dispatcher import _dispatcher_cache, _key_builder, build_dispatcher

# Two tenants' bots. Real bot ids are parsed from each tenant's own token
# (aiogram's extract_bot_id), so distinct tenants always have distinct ids.
TENANT_A_BOT_ID = 1111111
TENANT_B_BOT_ID = 2222222

# One Telegram customer. In a private chat under the default
# FSMStrategy.USER_IN_CHAT, chat_id == user_id — the case that collided.
CUSTOMER_ID = 111


def _key(bot_id: int) -> StorageKey:
    return StorageKey(bot_id=bot_id, chat_id=CUSTOMER_ID, user_id=CUSTOMER_ID)


@pytest.fixture(autouse=True)
def _clear_dispatcher_cache():
    _dispatcher_cache.clear()
    yield
    _dispatcher_cache.clear()


def test_key_builder_includes_the_bot_id():
    assert _key_builder().with_bot_id is True


def test_same_customer_in_two_tenants_gets_different_state_keys():
    """The regression itself: before the fix both sides built
    'fsm:111:111:...' and one customer had one shared state bucket across
    every pharmacy on the platform."""
    builder = _key_builder()

    for part in ("state", "data", "lock"):
        key_a = builder.build(_key(TENANT_A_BOT_ID), part)
        key_b = builder.build(_key(TENANT_B_BOT_ID), part)
        assert key_a != key_b, f"{part} key collides across tenants: {key_a}"
        assert str(TENANT_A_BOT_ID) in key_a
        assert str(TENANT_B_BOT_ID) in key_b


def test_the_dispatchers_storage_actually_uses_the_isolated_key_builder():
    """Guards the wiring, not just the helper — build_dispatcher() must
    pass the builder into RedisStorage rather than letting aiogram fall
    back to its own with_bot_id=False default."""

    async def _build():
        return build_dispatcher()

    dp = asyncio.run(_build())
    assert dp.storage.key_builder.with_bot_id is True


@pytest.mark.parametrize("part", ["state", "data"])
def test_state_written_for_tenant_a_is_not_readable_by_tenant_b(part):
    """Round trip through the real RedisStorage: what tenant A writes must
    be invisible to tenant B, and clearing B must not disturb A."""
    from aiogram.fsm.storage.redis import RedisStorage

    storage = RedisStorage.from_url(settings.REDIS_URL, key_builder=_key_builder())
    key_a, key_b = _key(TENANT_A_BOT_ID), _key(TENANT_B_BOT_ID)

    async def _exercise():
        try:
            # Start clean — Redis is shared and not rolled back between tests.
            await storage.set_state(key_a, None)
            await storage.set_state(key_b, None)
            await storage.set_data(key_a, {})
            await storage.set_data(key_b, {})

            if part == "state":
                await storage.set_state(key_a, "RedeemStates:awaiting_amount")
                leaked = await storage.get_state(key_b)
            else:
                # The registration payload: leaking this across tenants is
                # what lets a phone captured in tenant A be consented to in
                # tenant B.
                await storage.set_data(key_a, {"phone": "+998901234567", "language": "uz"})
                leaked = await storage.get_data(key_b) or None

            mine = (
                await storage.get_state(key_a)
                if part == "state"
                else await storage.get_data(key_a)
            )
            return leaked, mine
        finally:
            await storage.close()

    leaked, mine = asyncio.run(_exercise())

    assert leaked is None, f"tenant B read tenant A's {part}: {leaked!r}"
    assert mine, "tenant A lost its own state"


def test_clearing_state_in_tenant_b_leaves_tenant_a_untouched():
    """`state.clear()` runs on every /start, cancel and completed flow, so
    a shared key meant one bot routinely wiped the other's live state."""
    from aiogram.fsm.storage.redis import RedisStorage

    storage = RedisStorage.from_url(settings.REDIS_URL, key_builder=_key_builder())
    key_a, key_b = _key(TENANT_A_BOT_ID), _key(TENANT_B_BOT_ID)

    async def _exercise():
        try:
            await storage.set_state(key_a, "SettingsStates:awaiting_name")
            await storage.set_data(key_a, {"phone": "+998901234567"})

            # Tenant B's bot clears — the equivalent of on_cancel/cmd_start.
            await storage.set_state(key_b, None)
            await storage.set_data(key_b, {})

            return await storage.get_state(key_a), await storage.get_data(key_a)
        finally:
            await storage.set_state(key_a, None)
            await storage.set_data(key_a, {})
            await storage.close()

    state_a, data_a = asyncio.run(_exercise())

    assert state_a == "SettingsStates:awaiting_name"
    assert data_a == {"phone": "+998901234567"}


def test_normal_single_tenant_fsm_behaviour_still_works():
    """The fix must not change how state behaves within one bot: set,
    read back, overwrite, clear."""
    from aiogram.fsm.storage.redis import RedisStorage

    storage = RedisStorage.from_url(settings.REDIS_URL, key_builder=_key_builder())
    key = _key(TENANT_A_BOT_ID)

    async def _exercise():
        try:
            await storage.set_state(key, "RedeemStates:awaiting_amount")
            first = await storage.get_state(key)

            await storage.update_data(key, {"language": "en"})
            await storage.update_data(key, {"phone": "+998901234567"})
            merged = await storage.get_data(key)

            await storage.set_state(key, None)
            await storage.set_data(key, {})
            return first, merged, await storage.get_state(key), await storage.get_data(key)
        finally:
            await storage.close()

    first, merged, cleared_state, cleared_data = asyncio.run(_exercise())

    assert first == "RedeemStates:awaiting_amount"
    assert merged == {"language": "en", "phone": "+998901234567"}
    assert cleared_state is None
    assert cleared_data == {}
