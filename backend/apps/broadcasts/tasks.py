"""Celery task for broadcast sending (CLAUDE.md §9: throttled to ~25 msg/sec
— Telegram's real ceiling is ~30/sec, 25 leaves headroom for jitter).

Sync Django ORM writes (broadcast/customer updates) happen strictly before
and after the asyncio.run() block, never inside it — mirroring
apps/bot/tasks.py's split, since calling sync ORM methods while an asyncio
event loop is running raises Django's SynchronousOnlyOperation regardless of
whether we're in a request or a Celery task.

Per-recipient errors are classified into three buckets, matching
BroadcastDeliveryLog.Status:
  - blocked: TelegramForbiddenError — permanent, the customer is deactivated
    so future broadcasts skip them (unchanged from before).
  - failed: anything else, including flood control (TelegramRetryAfter)
    that didn't resolve within MAX_ATTEMPTS retries — transient in
    principle, but this task doesn't requeue individual recipients across
    separate task runs, so "failed" here means "not delivered this run."
  - success: sent.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile
from celery import shared_task
from django.utils import timezone

from apps.bot.telegram_client import build_client
from apps.broadcasts.models import Broadcast, BroadcastDeliveryLog, BroadcastMedia
from apps.broadcasts.sanitizer import render_broadcast_message_html
from apps.customers.models import Customer
from apps.tenants.models import Bot as BotRow

logger = logging.getLogger(__name__)

MESSAGES_PER_SECOND = 25
# First attempt + up to this many retries after a 429/flood-control
# response, sleeping for Telegram's own `retry_after` each time.
MAX_ATTEMPTS = 4


@dataclass
class _RecipientOutcome:
    customer_id: int
    status: str
    error_detail: str = ""


@dataclass
class _SendResult:
    outcomes: list[_RecipientOutcome] = field(default_factory=list)
    blocked_customer_ids: list[int] = field(default_factory=list)

    @property
    def sent(self) -> int:
        return sum(1 for o in self.outcomes if o.status == BroadcastDeliveryLog.Status.SUCCESS)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.status != BroadcastDeliveryLog.Status.SUCCESS)


async def _send_one(bot, broadcast: Broadcast, customer: Customer) -> _RecipientOutcome:
    text = render_broadcast_message_html(broadcast.title, broadcast.body)
    media = broadcast.media
    last_retry_after = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if media is None:
                await bot.send_message(customer.telegram_id, text, parse_mode="HTML")
            elif media.media_type == BroadcastMedia.MediaType.IMAGE:
                await bot.send_photo(
                    customer.telegram_id,
                    FSInputFile(media.file.path),
                    caption=text,
                    parse_mode="HTML",
                )
            else:
                await bot.send_video(
                    customer.telegram_id,
                    FSInputFile(media.file.path),
                    caption=text,
                    parse_mode="HTML",
                )
            return _RecipientOutcome(customer.pk, BroadcastDeliveryLog.Status.SUCCESS)
        except TelegramRetryAfter as exc:
            last_retry_after = exc.retry_after
            if attempt == MAX_ATTEMPTS:
                break
            logger.info(
                "Broadcast %s: flood control for customer %s, sleeping %ss (attempt %s/%s)",
                broadcast.pk,
                customer.pk,
                exc.retry_after,
                attempt,
                MAX_ATTEMPTS,
            )
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            return _RecipientOutcome(
                customer.pk, BroadcastDeliveryLog.Status.BLOCKED, "Bot blocked by user."
            )
        except Exception as exc:  # noqa: BLE001 — must never crash the whole batch
            logger.exception(
                "Broadcast %s: failed to send to customer %s", broadcast.pk, customer.pk
            )
            return _RecipientOutcome(customer.pk, BroadcastDeliveryLog.Status.FAILED, str(exc))

    return _RecipientOutcome(
        customer.pk,
        BroadcastDeliveryLog.Status.FAILED,
        f"Flood control: retry_after={last_retry_after}s, gave up after {MAX_ATTEMPTS} attempts.",
    )


async def _send_all(
    bot_row: BotRow, broadcast: Broadcast, recipients: list[Customer]
) -> _SendResult:
    result = _SendResult()
    async with build_client(bot_row) as bot:
        for customer in recipients:
            outcome = await _send_one(bot, broadcast, customer)
            result.outcomes.append(outcome)
            if outcome.status == BroadcastDeliveryLog.Status.BLOCKED:
                result.blocked_customer_ids.append(customer.pk)
            # Constant per-message spacing at MESSAGES_PER_SECOND *is* the
            # batching/throttling strategy — smoother than bursty
            # chunk-then-sleep, and Telegram's 429 handling above still
            # covers the case where even this pace trips flood control.
            await asyncio.sleep(1 / MESSAGES_PER_SECOND)
    return result


@shared_task
def send_broadcast(broadcast_id: int) -> None:
    broadcast = (
        Broadcast.objects.all_tenants().select_related("tenant", "media").get(pk=broadcast_id)
    )
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

    try:
        result = asyncio.run(_send_all(bot_row, broadcast, recipients))
    except Exception:
        # Something broke outside per-recipient handling (e.g. the bot
        # client itself failed to build) — mark it clearly rather than
        # leaving the broadcast stuck in "sending" forever. Not re-raised:
        # Celery retrying this task would re-send to everyone who already
        # got it, since we don't track per-recipient completion across runs.
        logger.exception("Broadcast %s: send task crashed.", broadcast_id)
        broadcast.status = Broadcast.Status.FAILED
        broadcast.save(update_fields=["status"])
        return

    BroadcastDeliveryLog.objects.all_tenants().bulk_create(
        BroadcastDeliveryLog(
            tenant_id=broadcast.tenant_id,
            broadcast=broadcast,
            customer_id=outcome.customer_id,
            status=outcome.status,
            error_detail=outcome.error_detail,
        )
        for outcome in result.outcomes
    )

    broadcast.sent_count = result.sent
    broadcast.failed_count = result.failed
    broadcast.status = Broadcast.Status.SENT
    broadcast.sent_at = timezone.now()
    broadcast.save(update_fields=["sent_count", "failed_count", "status", "sent_at"])

    if result.blocked_customer_ids:
        Customer.objects.all_tenants().filter(pk__in=result.blocked_customer_ids).update(
            is_active=False
        )
