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

# Matches apps/bot/qr.py's is_trusted_check_url pattern — check_url is
# already validated as an ofd.soliq.uz /check URL before this is ever
# called (apps.bot.services.handle_receipt_photo), but the response
# listener below still only reacts to the one endpoint it's looking for.
_RECEIPT_API_PATH = "/api/payment"


async def _fetch_receipt_via_playwright(check_url: str) -> dict | None:
    """Reads a fiscal receipt's sale totals off ofd.soliq.uz.

    The check page's own JS signs its call to new-ofd.soliq.uz/api/payment
    with an x-signature/x-timestamp header computed client-side — a plain
    HTTP request to that endpoint without it is rejected (verified: 400).
    Reproducing that signature would mean reverse-engineering their
    anti-abuse protection, which this deliberately avoids; instead a real
    (headless) browser loads the actual page and lets *it* make the
    signed request, and this just listens for the JSON response that
    request gets back — the same thing a real customer's browser does.

    Returns only the fields apps.bot.services.handle_receipt_photo needs
    (None if the page never returned a usable payment payload, e.g. a
    malformed/expired check URL, or the fetch timed out/errored)."""
    from playwright.async_api import async_playwright

    payload: dict | None = None

    async def _capture_response(response):
        nonlocal payload
        if _RECEIPT_API_PATH not in response.url:
            return
        if "application/json" not in response.headers.get("content-type", ""):
            return
        try:
            payload = await response.json()
        except Exception:
            return

    # ofd.soliq.uz silently drops connections from outside Uzbekistan
    # (verified: a raw TCP connect from a France-hosted server times out at
    # the handshake — this isn't the site being slow or anti-bot-challenging
    # a headless browser, the SYN itself never gets a response). A server
    # hosted outside Uzbekistan needs an Uzbek egress point for this one
    # call; see config.settings.OFD_PROXY_URL for the env var this reads.
    # Playwright's browser-level proxy applies to every request the browser
    # makes, which is fine here — this browser instance exists solely to
    # load check_url, nothing else runs through it.
    launch_kwargs: dict = {"headless": True}
    if settings.OFD_PROXY_URL:
        proxy: dict = {"server": settings.OFD_PROXY_URL}
        if settings.OFD_PROXY_USERNAME:
            proxy["username"] = settings.OFD_PROXY_USERNAME
        if settings.OFD_PROXY_PASSWORD:
            proxy["password"] = settings.OFD_PROXY_PASSWORD
        launch_kwargs["proxy"] = proxy

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(**launch_kwargs)
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                page.on("response", _capture_response)
                await page.goto(check_url, wait_until="networkidle", timeout=15000)
                # The page's own JS fires the signed API call asynchronously
                # after load — wait_until="networkidle" alone occasionally
                # races ahead of it, same margin experiment.py's manual
                # testing needed.
                await page.wait_for_timeout(1500)
            finally:
                await browser.close()
    except Exception:
        # Best-effort, same "log and don't propagate" posture as every
        # other external-call task in this module — a flaky/unreachable
        # ofd.soliq.uz must not crash the Celery task, just fail this scan.
        logger.exception("Failed to fetch receipt data from %s", check_url)
        return None

    if payload is None or not payload.get("success"):
        return None
    data = payload.get("data") or {}
    if not data:
        return None
    return {
        "tin": data.get("tin"),
        "cash_total": data.get("cashTotal"),
        "card_total": data.get("cardTotal"),
        "terminal_id": data.get("terminalId"),
        "payment_no": data.get("paymentNo"),
    }


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


def _sync_bot_display_name_sync(bot_id: int, new_name: str) -> None:
    bot_row = BotRow.objects.all_tenants().filter(pk=bot_id, is_active=True).first()
    if bot_row is None or not bot_row.token_encrypted:
        return

    async def _set():
        async with build_client(bot_row) as bot:
            # Telegram's setMyName caps at 64 chars — Tenant.name allows up
            # to 255, so truncate rather than let the call fail outright.
            await bot.set_my_name(name=new_name[:64])

    try:
        asyncio.run(_set())
    except TelegramAPIError:
        # Best-effort: the tenant rename itself already succeeded and is
        # not rolled back just because Telegram's side of the sync failed
        # (e.g. bot token revoked) — same "log and move on" posture as the
        # old-webhook cleanup in rotate_bot_credentials above.
        logger.info("Could not sync bot display name for bot %s.", bot_id)


@shared_task
def sync_bot_display_name(bot_id: int, new_name: str) -> None:
    """Fired when a tenant renames their pharmacy (apps/tenants/api_views.py
    TenantViewSet.perform_update) — pushes the new name to Telegram as the
    bot's own display name (distinct from Bot.username, the @handle, which
    only BotFather can change) so customers see the pharmacy's current name
    in the chat, not whatever it was called when the bot was first added."""
    _sync_bot_display_name_sync(bot_id, new_name)


def _process_receipt_photo_sync(
    *, tenant_id: int, customer_id: int, chat_id: int, bot_id: int, check_url: str
) -> None:
    from apps.bot.qr import is_trusted_check_url
    from apps.bot.services import handle_receipt_check_data
    from apps.customers.models import Customer
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.get(pk=tenant_id)
    customer = Customer.objects.all_tenants().get(pk=customer_id, tenant_id=tenant_id)
    bot_row = BotRow.objects.all_tenants().filter(pk=bot_id, is_active=True).first()
    if bot_row is None or not bot_row.token_encrypted:
        return

    # Re-checked here (defense in depth) — apps.bot.handlers.on_receipt_photo
    # already validates this before ever queuing the task, but check_url is
    # a plain string argument, not a type the task itself can trust blindly.
    if not is_trusted_check_url(check_url):
        return

    check_data = asyncio.run(_fetch_receipt_via_playwright(check_url))
    message: str | None
    if check_data is None:
        from apps.bot.i18n import t

        message = t(customer.language, "receipt_fetch_failed")
    else:
        message = handle_receipt_check_data(tenant=tenant, customer=customer, check_data=check_data)

    if message is None:
        # Success — post_earn_transaction's on_commit hook already fired
        # the usual notify_transaction task, so there's nothing left to say.
        return

    async def _send():
        async with build_client(bot_row) as bot:
            await bot.send_message(chat_id, message)

    asyncio.run(_send())


@shared_task
def process_receipt_photo(
    *, tenant_id: int, customer_id: int, chat_id: int, bot_id: int, check_url: str
) -> None:
    """Bot-only QR-receipt cashback flow (apps/bot/qr.py,
    apps/bot/services.py::handle_receipt_check_data): fired from
    apps.bot.handlers.on_receipt_photo after a customer sends a photo whose
    QR decodes to a trusted ofd.soliq.uz check URL. Runs in the worker, not
    the webhook handler, because reading the receipt needs a real
    headless-browser page load (a few seconds) — the customer already got
    an immediate "tekshirilmoqda" ack before this was queued."""
    _process_receipt_photo_sync(
        tenant_id=tenant_id,
        customer_id=customer_id,
        chat_id=chat_id,
        bot_id=bot_id,
        check_url=check_url,
    )
