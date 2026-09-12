"""One shared Router for ALL tenant bots (CLAUDE.md §7a multibot), holding
just the handler registrations — safe as a module-level singleton since it
holds no live connections.

The FSM Dispatcher/RedisStorage used to be rebuilt from scratch on every
single webhook request. That was a deliberate (if costly) tradeoff: each
webhook POST to this async view is bridged from Django's request handling
via asgiref.async_to_sync, which historically meant "maybe a new event
loop per request" — true under `manage.py runserver` (not a real ASGI
server, only bridges per-view), and a persistent redis-py async connection
created in one such loop breaks on the next request if that next request
runs in a different loop.

Under the real production server (uvicorn, docker-compose.prod.yml), an
async Django view runs directly on uvicorn's own already-running event
loop — there's no per-request loop churn there at all, so every webhook
request in a given worker process shares the same loop, and rebuilding the
Dispatcher/RedisStorage (and its Redis connection) from scratch each time
was pure waste. build_dispatcher below now caches by the current running
loop instead: same loop as last time -> reuse; different loop (or first
call) -> build fresh and drop the old cache entry.

Note the old entry's storage is not explicitly closed when evicted this
way — its loop is what it would need to close cleanly, and if the loop
changed, there's no live loop left to close it *on*. This is a non-issue
under uvicorn, where the loop never changes and eviction never happens; it
only means dev/runserver traffic (where the loop can differ per request)
may abandon a spare Redis connection per switch, not leak indefinitely.
"""

import asyncio

from aiogram import Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from django.conf import settings

from apps.bot import handlers

_dispatcher_cache: dict[asyncio.AbstractEventLoop, Dispatcher] = {}


def _key_builder() -> DefaultKeyBuilder:
    """FSM keys MUST carry the bot id — this is a multibot process
    (CLAUDE.md §4/§7a), and without it every tenant's bot shares one state
    bucket per Telegram user.

    aiogram's `DefaultKeyBuilder` defaults to `with_bot_id=False`, and
    `RedisStorage.__init__` falls back to exactly that default when no
    `key_builder` is passed — which is what this code used to do. The
    resulting Redis key is `fsm:<chat_id>:<user_id>:<part>`, with
    `StorageKey.bot_id` silently dropped even though
    `FSMContextMiddleware.get_context` does populate it from `bot.id`.
    Under the default `FSMStrategy.USER_IN_CHAT` a private chat has
    `chat_id == user_id`, so one customer talking to two different
    pharmacies' bots resolved to one and the same key — verified against
    the installed aiogram 3.15.0: both tenants produced `fsm:111:111:data`.
    That leaked the phone/full_name captured mid-registration in one
    tenant into the other's registration flow, let a `RedeemStates`
    transition set by one bot capture the next message sent to the other,
    and made `state.clear()` in either bot wipe both.
    `bot.id` is parsed from the tenant's own bot token, so it is a real
    per-tenant discriminator here, not a cosmetic prefix.

    Passing the same builder to the storage also covers the lock keys:
    `RedisStorage.create_isolation()` hands its own `key_builder` to
    `RedisEventIsolation`. (This `Dispatcher` is built without an
    `events_isolation`, so aiogram uses `DisabledEventIsolation` and no
    lock key is taken today — this just means the fix stays correct if
    isolation is ever switched on.)

    DEPLOY NOTE: this changes the key namespace, so FSM state in flight at
    deploy time is not carried over. That is a deliberate, graceful reset,
    not data loss — a customer mid-registration falls into
    `on_consent_accept`'s existing "no phone in state" branch and is told
    to send /start again; nothing durable lives in FSM state (the ledger,
    Customer and PendingCashback rows are all in Postgres). The orphaned
    `fsm:<chat_id>:<user_id>:*` keys are written without a TTL, so they
    stay in Redis until deleted; they are inert, and clearing them is a
    housekeeping step, not part of this fix.
    """
    return DefaultKeyBuilder(with_bot_id=True)


def build_dispatcher() -> Dispatcher:
    loop = asyncio.get_running_loop()
    cached = _dispatcher_cache.get(loop)
    if cached is not None:
        return cached

    _dispatcher_cache.clear()  # drop whatever loop's entry we had before
    storage = RedisStorage.from_url(settings.REDIS_URL, key_builder=_key_builder())
    dp = Dispatcher(storage=storage)
    handlers.register_handlers(dp)
    _dispatcher_cache[loop] = dp
    return dp
