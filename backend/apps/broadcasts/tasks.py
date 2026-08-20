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
from django.core.files.base import ContentFile
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.bot.telegram_client import build_client
from apps.broadcasts.models import (
    Broadcast,
    BroadcastDeliveryLog,
    BroadcastMedia,
    PlatformBroadcast,
)
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
    # apps.broadcasts.api_views.BroadcastViewSet.perform_destroy blocks
    # deleting a non-DRAFT broadcast through the normal API, but that's a
    # guard against the common path (a tenant admin deleting their own
    # broadcast), not a database constraint — Django admin (BroadcastAdmin)
    # and direct shell/ORM access can still delete this row between .delay()
    # being called and this task actually running. That race is real even
    # with the API guard in place, so it's handled here rather than left to
    # crash the task and show up as an unhandled Celery error.
    try:
        broadcast = (
            Broadcast.objects.all_tenants().select_related("tenant", "media").get(pk=broadcast_id)
        )
    except Broadcast.DoesNotExist:
        logger.warning(
            "Broadcast %s: no longer exists (deleted before this task ran?), skipping.",
            broadcast_id,
        )
        return
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


def _copy_media_for_tenant(src, tenant, uploaded_by) -> BroadcastMedia:
    """Duplicates a superadmin-authored PlatformBroadcastMedia into a fresh
    tenant-scoped BroadcastMedia row, so each tenant leg of a platform
    broadcast owns its own file under the normal tenant-scoped storage path
    — mirrors the isolation-boundary comment on broadcast_media_upload_path
    (the boundary is the queryset, not the path, but every tenant still
    needs its own row to be reachable through that queryset at all)."""
    media = BroadcastMedia(
        tenant=tenant,
        media_type=src.media_type,
        original_filename=src.original_filename,
        content_type=src.content_type,
        size_bytes=src.size_bytes,
        uploaded_by=uploaded_by,
    )
    with src.file.open("rb") as fh:
        media.file.save(src.original_filename, ContentFile(fh.read()), save=False)
    media.save()
    return media


@shared_task
def send_platform_broadcast(platform_broadcast_id: int) -> None:
    """Fans a superadmin's PlatformBroadcast out to every active tenant that
    has an active, tokened bot: creates one tenant-scoped Broadcast leg per
    tenant (already in SENDING status — never DRAFT, see below) and hands
    each off to the existing, unchanged send_broadcast task for actual
    delivery. Reuses that task's throttling/retry/delivery-log/
    blocked-customer handling completely rather than reimplementing any of
    it here.

    Legs are created as SENDING, not the model-default DRAFT: a DRAFT leg
    would sit fully visible (and clickable) in the owning tenant's own
    GET /api/broadcasts/ list for the whole gap between this task creating
    it and send_broadcast actually running, letting that tenant's own
    tenant_admin click "Send" on it first and double-enqueue delivery to
    their own customers. Creating it already-SENDING in one atomic INSERT
    closes that window entirely, and BroadcastViewSet.send()'s existing
    "only a draft can be sent" guard rejects any such attempt for free.

    Each tenant's leg is wrapped in its own try/except: one tenant's media
    copy or DB error must not abort dispatch to every other tenant queued
    after it.
    """
    platform_broadcast = PlatformBroadcast.objects.select_related("media").get(
        pk=platform_broadcast_id
    )

    # Sourced from Bot (not Tenant) so "is this tenant sendable" uses
    # exactly the same criteria send_broadcast itself checks
    # (bot_row is None or not bot_row.token_encrypted) — one definition of
    # "sendable," not two that can quietly drift apart.
    bots = (
        BotRow.objects.all_tenants()
        .filter(is_active=True, tenant__is_active=True)
        .exclude(token_encrypted="")
        .select_related("tenant")
    )

    dispatched = 0
    for bot_row in bots:
        tenant = bot_row.tenant
        try:
            with db_transaction.atomic():
                media = (
                    _copy_media_for_tenant(
                        platform_broadcast.media, tenant, platform_broadcast.created_by
                    )
                    if platform_broadcast.media
                    else None
                )
                leg = Broadcast.objects.all_tenants().create(
                    tenant=tenant,
                    title=platform_broadcast.title,
                    body=platform_broadcast.body,
                    media=media,
                    created_by=platform_broadcast.created_by,
                    platform_broadcast=platform_broadcast,
                    status=Broadcast.Status.SENDING,
                )
        except Exception:
            logger.exception(
                "Platform broadcast %s: failed to dispatch for tenant %s",
                platform_broadcast_id,
                tenant.pk,
            )
            continue

        send_broadcast.delay(leg.pk)
        dispatched += 1

    platform_broadcast.status = (
        PlatformBroadcast.Status.SENT if dispatched else PlatformBroadcast.Status.FAILED
    )
    platform_broadcast.sent_at = timezone.now()
    platform_broadcast.save(update_fields=["status", "sent_at"])
