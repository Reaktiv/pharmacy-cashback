"""Celery tasks for the Telegram bot (CLAUDE.md §9: Celery + Redis).

Each task fetches everything it needs via plain sync Django ORM first, then
enters a short-lived asyncio.run() block just for the outbound Telegram
call — there's no ambient async context in a Celery worker process, so this
doesn't hit the sync/async issues the webhook view has to work around.
"""

import asyncio
import logging

from celery import shared_task
from django.conf import settings

from apps.bot.telegram_client import build_client
from apps.ledger.models import Transaction
from apps.tenants.models import Bot as BotRow

logger = logging.getLogger(__name__)


def _report_keyboard(transaction_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Wrong amount? Report", callback_data=f"report:{transaction_id}"
                )
            ]
        ]
    )


def _notify_transaction_sync(transaction_id: int) -> None:
    from apps.bot.services import format_notification_text

    txn = (
        Transaction.objects.all_tenants()
        .select_related("customer", "tenant")
        .get(pk=transaction_id)
    )
    customer = txn.customer
    if not customer.telegram_id:
        return  # not registered yet — nothing to notify

    bot_row = (
        BotRow.objects.all_tenants().filter(tenant_id=txn.tenant_id, is_active=True).first()
    )
    if bot_row is None or not bot_row.token_encrypted:
        return

    text = format_notification_text(txn)
    keyboard = _report_keyboard(txn.pk)

    async def _send():
        async with build_client(bot_row) as bot:
            await bot.send_message(customer.telegram_id, text, reply_markup=keyboard)

    asyncio.run(_send())


def _register_webhook_sync(bot_row: BotRow) -> None:
    if not bot_row.token_encrypted:
        logger.warning("Bot %s has no token set — skipping webhook registration.", bot_row.pk)
        return

    url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/webhook/{bot_row.webhook_secret}/"

    async def _set():
        async with build_client(bot_row) as bot:
            await bot.set_webhook(url=url)

    asyncio.run(_set())


@shared_task
def notify_transaction(transaction_id: int) -> None:
    """CLAUDE.md §7a auto-notification, fired by post_earn_transaction /
    post_reversal (apps/ledger/services.py) after commit."""
    _notify_transaction_sync(transaction_id)


@shared_task
def register_webhook(bot_id: int) -> None:
    """Fired by the Bot post_save signal (apps/bot/signals.py) so adding a
    Bot row auto-registers its webhook with no redeploy."""
    bot_row = BotRow.objects.all_tenants().get(pk=bot_id)
    _register_webhook_sync(bot_row)
