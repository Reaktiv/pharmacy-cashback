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
from aiogram.fsm.storage.redis import RedisStorage
from django.conf import settings

from apps.bot import handlers

_dispatcher_cache: dict[asyncio.AbstractEventLoop, Dispatcher] = {}


def build_dispatcher() -> Dispatcher:
    loop = asyncio.get_running_loop()
    cached = _dispatcher_cache.get(loop)
    if cached is not None:
        return cached

    _dispatcher_cache.clear()  # drop whatever loop's entry we had before
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)
    handlers.register_handlers(dp)
    _dispatcher_cache[loop] = dp
    return dp
