"""One shared Router for ALL tenant bots (CLAUDE.md §7a multibot), holding
just the handler registrations — safe as a module-level singleton since it
holds no live connections.

The FSM Dispatcher/RedisStorage is built fresh per request instead (see
build_dispatcher, used by apps/bot/views.py) rather than as a module-level
singleton. Reason: each webhook POST to this async view is bridged from
Django's request handling via asgiref.async_to_sync, which runs it in its
own event loop — true even under `manage.py runserver`, since it isn't a
real ASGI server and only bridges per-view. A persistent redis-py async
connection created in one such loop breaks on the next request, which runs
in a different loop. Building storage per-request avoids that entirely, at
the cost of a small per-request connection setup — acceptable for webhook
traffic (one request at a time, not a hot loop).
"""

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from django.conf import settings

from apps.bot import handlers


def build_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)
    handlers.register_handlers(dp)
    return dp
