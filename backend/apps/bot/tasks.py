"""Celery tasks for the Telegram bot (CLAUDE.md §9: Celery + Redis).

Each task fetches everything it needs via plain sync Django ORM first, then
enters a short-lived asyncio.run() block just for the outbound Telegram
call — there's no ambient async context in a Celery worker process, so this
doesn't hit the sync/async issues the webhook view has to work around.
"""

import asyncio
import logging

from aiogram.exceptions import TelegramAPIError
from celery import shared_task
from django.conf import settings

from apps.bot.telegram_client import build_client, build_client_from_token
from apps.ledger.models import Transaction
from apps.tenants.models import Bot as BotRow

logger = logging.getLogger(__name__)


def _report_keyboard(transaction_id: int, language: str):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from apps.bot.i18n import t

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "report_button"),
                    callback_data=f"report:{transaction_id}",
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
    keyboard = _report_keyboard(txn.pk, customer.language)

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


def _rotate_bot_credentials_sync(bot_id: int, old_token: str) -> None:
    bot_row = BotRow.objects.all_tenants().get(pk=bot_id)

    async def _do() -> str | None:
        # Telegram doesn't clear the OLD bot's webhook just because a
        # different bot registers the same URL — without this, the old
        # bot keeps forwarding updates here too, and they get answered
        # using the tenant's new (current) token, which looks like "I
        # messaged the old bot but the new bot replied."
        try:
            async with build_client_from_token(old_token) as old_bot:
                await old_bot.delete_webhook()
        except TelegramAPIError:
            # Old token may already be invalid/revoked — nothing to clean
            # up on Telegram's side in that case, and that's fine.
            logger.info(
                "Could not delete the old webhook for bot %s (token may already be revoked).",
                bot_id,
            )

        # The username belongs to whichever bot the token actually
        # authenticates as — refresh it from Telegram rather than trust
        # whatever was left over from before the rotation.
        async with build_client(bot_row) as new_bot:
            me = await new_bot.get_me()
        return me.username

    # The ORM save has to happen back in sync land — Django forbids sync
    # DB calls from inside the async block above.
    new_username = asyncio.run(_do())
    if new_username and new_username != bot_row.username:
        bot_row.username = new_username
        bot_row.save(update_fields=["username"])


@shared_task
def rotate_bot_credentials(bot_id: int, old_token: str) -> None:
    """Fired when a Bot's token is rotated (apps/tenants/api_views.py):
    deregisters the old token's webhook and refreshes the stored username
    to match the new token's actual bot identity."""
    _rotate_bot_credentials_sync(bot_id, old_token)
