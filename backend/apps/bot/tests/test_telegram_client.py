from types import SimpleNamespace
from unittest.mock import patch

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

from apps.bot.telegram_client import TelegramTokenValidationError, validate_bot_token


class _FakeAiogramBot:
    """Stands in for aiogram.Bot as an async context manager, returning a
    canned getMe() result (or raising a canned error) instead of hitting the
    real Telegram API."""

    def __init__(self, me=None, error=None):
        self._me = me
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_me(self):
        if self._error is not None:
            raise self._error
        return self._me


@pytest.mark.parametrize(
    "token",
    [
        "no-colon-at-all",
        "123456:abc:def",  # two colons
        "12a456:REAL-LOOKING-SECRET",  # non-digit bot id
        "123456:",  # empty secret
        "",
    ],
)
def test_rejects_malformed_token_without_ever_calling_telegram(token):
    with patch("apps.bot.telegram_client.build_client_from_token") as mock_build:
        with pytest.raises(TelegramTokenValidationError, match="Invalid token format."):
            validate_bot_token(token)
    mock_build.assert_not_called()


def test_rejects_a_token_telegram_says_is_unauthorized():
    fake_bot = _FakeAiogramBot(
        error=TelegramUnauthorizedError(method=None, message="Unauthorized")
    )
    with patch("apps.bot.telegram_client.build_client_from_token", return_value=fake_bot):
        with pytest.raises(TelegramTokenValidationError, match="Telegram rejected this token."):
            validate_bot_token("123456:REAL-LOOKING-SECRET")


def test_maps_a_network_failure_to_a_retry_later_message():
    fake_bot = _FakeAiogramBot(error=TelegramNetworkError(method=None, message="boom"))
    with patch("apps.bot.telegram_client.build_client_from_token", return_value=fake_bot):
        with pytest.raises(TelegramTokenValidationError, match="Unable to contact Telegram API"):
            validate_bot_token("123456:REAL-LOOKING-SECRET")


def test_rejects_a_token_whose_embedded_id_does_not_match_getme():
    fake_bot = _FakeAiogramBot(me=SimpleNamespace(id=999999, username="someone_elses_bot"))
    with patch("apps.bot.telegram_client.build_client_from_token", return_value=fake_bot):
        with pytest.raises(TelegramTokenValidationError, match="Bot ID mismatch"):
            validate_bot_token("123456:REAL-LOOKING-SECRET")


def test_accepts_a_valid_token_and_returns_its_real_username():
    fake_bot = _FakeAiogramBot(me=SimpleNamespace(id=123456, username="pharmacy_cashback_bot"))
    with patch(
        "apps.bot.telegram_client.build_client_from_token", return_value=fake_bot
    ) as mock_build:
        username = validate_bot_token("123456:REAL-LOOKING-SECRET")

    assert username == "pharmacy_cashback_bot"
    # Validation runs inline in a web request, not a background worker, so
    # it must use a short timeout rather than aiogram's 60s session default.
    mock_build.assert_called_once_with("123456:REAL-LOOKING-SECRET", timeout=10.0)
