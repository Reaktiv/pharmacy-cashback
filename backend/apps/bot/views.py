"""Multibot webhook (CLAUDE.md §7a / §4). Tenant is resolved from the
webhook_secret path component, never from the bot token — the token must
never appear in a URL or log.
"""

import json
import logging

from aiogram.types import Update
from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.bot.dispatcher import build_dispatcher
from apps.bot.telegram_client import build_client
from apps.tenants.context import reset_current_tenant, set_current_tenant
from apps.tenants.models import Bot as BotRow

logger = logging.getLogger(__name__)


def _get_active_bot(webhook_secret: str) -> BotRow | None:
    return (
        BotRow.objects.all_tenants()
        .select_related("tenant")
        .filter(webhook_secret=webhook_secret, is_active=True)
        .first()
    )


@csrf_exempt
async def webhook(request, webhook_secret: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)

    bot_row = await sync_to_async(_get_active_bot, thread_sensitive=True)(webhook_secret)
    if bot_row is None:
        return HttpResponse(status=404)

    tenant = bot_row.tenant

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    update = Update.model_validate(payload)

    # CLAUDE.md §4: bind the tenant ContextVar for this update's duration,
    # same as TenantMiddleware does for web requests. Handlers also receive
    # tenant explicitly (below) and don't rely on this ambient value — it's
    # here so the default TenantManager filtering works too if anything
    # queries through it.
    token = set_current_tenant(tenant)
    dp = build_dispatcher()
    try:
        async with build_client(bot_row) as bot:
            await dp.feed_update(bot, update, tenant=tenant, bot_row=bot_row)
    except Exception:
        logger.exception("Unhandled error processing Telegram update for tenant %s", tenant.id)
    finally:
        # dp.storage is no longer closed here — build_dispatcher (see
        # apps/bot/dispatcher.py) now reuses the same Dispatcher/storage
        # across requests on the same event loop, so closing it after
        # every request would break the very next one.
        reset_current_tenant(token)

    return HttpResponse(status=200)
