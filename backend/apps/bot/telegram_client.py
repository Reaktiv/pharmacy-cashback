"""Builds a per-tenant aiogram Bot instance (CLAUDE.md §7a multibot: one
process, many tokens). Never construct aiogram.Bot with a raw token
elsewhere — always go through here so decryption stays in one place."""

import asyncio

from aiogram import Bot as AiogramBot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError

from apps.tenants.models import Bot as BotRow

# Well under aiogram's 60s session default — validate_bot_token() below runs
# inline in a web request (the settings page must reject a bad token before
# it's ever saved), not in a Celery worker, so a slow/hanging Telegram API
# must not tie up a web worker for a full minute.
_VALIDATION_TIMEOUT = 10.0


def build_client(bot_row: BotRow) -> AiogramBot:
    return AiogramBot(token=bot_row.get_token())


def build_client_from_token(raw_token: str, *, timeout: float | None = None) -> AiogramBot:
    """Same as build_client, but for a raw token no longer backed by a
    BotRow — e.g. the old token being cleaned up right after a rotation
    (once the new one has already overwritten it in the DB), or a
    candidate token being live-checked before it's ever saved (see
    validate_bot_token below)."""
    session = AiohttpSession(timeout=timeout) if timeout is not None else None
    return AiogramBot(token=raw_token, session=session)


class TelegramTokenValidationError(Exception):
    """Raised by validate_bot_token() for any reason a candidate bot token
    can be rejected. str(exc) is a user-facing message."""


def validate_bot_token(raw_token: str) -> str:
    """The single place that decides whether a Telegram bot token is real.
    Used by both the bot settings API (apps/tenants/serializers.py) and the
    Django admin form (apps/tenants/admin.py) so "add a bot" and "replace an
    existing bot's token" can never drift out of sync on what counts as
    valid:

    1. Format: exactly one ':', a digits-only bot id before it, and a
       non-empty secret after it.
    2. Live check: call Telegram's getMe with the token.
    3. Identity check: the bot id embedded in the token must match the id
       Telegram reports back for it — catches a syntactically valid token
       for a DIFFERENT bot being pasted in by mistake.

    Returns the bot's real username (from Telegram, not user input) on
    success. Raises TelegramTokenValidationError with a user-facing message
    on any failure.
    """
    left, _sep, right = raw_token.partition(":")
    if raw_token.count(":") != 1 or not left.isdigit() or not right:
        raise TelegramTokenValidationError("Invalid token format.")
    token_bot_id = int(left)

    async def _get_me():
        async with build_client_from_token(raw_token, timeout=_VALIDATION_TIMEOUT) as bot:
            return await bot.get_me()

    try:
        me = asyncio.run(_get_me())
    except TelegramNetworkError:
        raise TelegramTokenValidationError(
            "Unable to contact Telegram API. Please try again later."
        ) from None
    except TelegramAPIError:
        raise TelegramTokenValidationError("Telegram rejected this token.") from None

    if me.id != token_bot_id:
        raise TelegramTokenValidationError("Bot ID mismatch. The token appears to be invalid.")

    return me.username
