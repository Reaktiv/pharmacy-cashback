"""Celery task for broadcast sending (CLAUDE.md §9: throttled to ~25 msg/sec
to respect Telegram's rate limits).

Sync Django ORM writes (broadcast/customer updates) happen strictly before
and after the asyncio.run() block, never inside it — mirroring
apps/bot/tasks.py's split, since calling sync ORM methods while an asyncio
event loop is running raises Django's SynchronousOnlyOperation regardless of
whether we're in a request or a Celery task.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from aiogram.exceptions import TelegramForbiddenError
from celery import shared_task

from apps.bot.telegram_client import build_client
from apps.broadcasts.models import Broadcast
from apps.customers.models import Customer
from apps.tenants.models import Bot as BotRow

logger = logging.getLogger(__name__)

MESSAGES_PER_SECOND = 25


@dataclass
class _SendResult:
    sent: int = 0
    failed: int = 0
    blocked_customer_ids: list[int] = field(default_factory=list)


async def _send_all(
    bot_row: BotRow, broadcast: Broadcast, recipients: list[Customer]
) -> _SendResult:
    result = _SendResult()
    text = f"{broadcast.title}\n\n{broadcast.body}"
    async with build_client(bot_row) as bot:
        for customer in recipients:
            try:
                await bot.send_message(customer.telegram_id, text)
                result.sent += 1
            except TelegramForbiddenError:
                # Customer blocked the bot — skip, don't crash the batch.
                result.failed += 1
                result.blocked_customer_ids.append(customer.pk)
            except Exception:
                logger.exception(
                    "Broadcast %s: failed to send to customer %s", broadcast.pk, customer.pk
                )
                result.failed += 1
            await asyncio.sleep(1 / MESSAGES_PER_SECOND)
    return result


@shared_task
def send_broadcast(broadcast_id: int) -> None:
    broadcast = Broadcast.objects.all_tenants().select_related("tenant").get(pk=broadcast_id)
    bot_row = (
        BotRow.objects.all_tenants().filter(tenant_id=broadcast.tenant_id, is_active=True).first()
    )
    if bot_row is None or not bot_row.token_encrypted:
        logger.warning("Broadcast %s: tenant has no active bot, aborting.", broadcast_id)
        return

    broadcast.status = Broadcast.Status.SENDING
    broadcast.save(update_fields=["status"])

    recipients = list(
        Customer.objects.all_tenants().filter(
            tenant_id=broadcast.tenant_id, is_active=True, telegram_id__isnull=False
        )
    )

    result = asyncio.run(_send_all(bot_row, broadcast, recipients))

    broadcast.sent_count = result.sent
    broadcast.failed_count = result.failed
    broadcast.status = Broadcast.Status.SENT
    broadcast.save(update_fields=["sent_count", "failed_count", "status"])

    if result.blocked_customer_ids:
        Customer.objects.all_tenants().filter(pk__in=result.blocked_customer_ids).update(
            is_active=False
        )
