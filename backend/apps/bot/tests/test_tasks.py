from decimal import Decimal
from unittest.mock import patch

import pytest
from aiogram.exceptions import TelegramAPIError

from apps.bot.tasks import (
    _notify_transaction_sync,
    _register_webhook_sync,
    _rotate_bot_credentials_sync,
    _sync_bot_display_name_sync,
)
from apps.ledger.services import post_earn_transaction
from apps.tenants.models import Bot


def _make_bot_row(tenant):
    bot_row = Bot.objects.all_tenants().create(tenant=tenant, username="@testbot")
    bot_row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    bot_row.save()
    return bot_row


class _FakeAiogramBot:
    """Stands in for aiogram.Bot as an async context manager, recording
    calls instead of hitting the real Telegram API."""

    def __init__(self, username=None):
        self.sent = []
        self.webhooks_set = []
        self.webhook_deleted = False
        self.names_set = []
        self._username = username

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    async def set_webhook(self, url):
        self.webhooks_set.append(url)

    async def delete_webhook(self):
        self.webhook_deleted = True

    async def get_me(self):
        from types import SimpleNamespace

        return SimpleNamespace(username=self._username)

    async def set_my_name(self, name=None):
        self.names_set.append(name)
        return True


@pytest.mark.django_db
def test_notify_transaction_sends_a_message_to_a_registered_customer(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    customer.telegram_id = 4242
    customer.save(update_fields=["telegram_id"])
    _make_bot_row(tenant)

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.bot.tasks.build_client", return_value=fake_bot):
        _notify_transaction_sync(txn.pk)

    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["chat_id"] == 4242
    assert "so'mlik xariddan 10000.00 ball qo'shildi" in fake_bot.sent[0]["text"]


@pytest.mark.django_db
def test_notify_transaction_is_a_noop_for_an_unregistered_customer(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)  # no telegram_id
    _make_bot_row(tenant)

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.bot.tasks.build_client", return_value=fake_bot):
        _notify_transaction_sync(txn.pk)

    assert fake_bot.sent == []


@pytest.mark.django_db
def test_notify_transaction_is_a_noop_when_the_tenant_has_no_bot(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    customer.telegram_id = 4242
    customer.save(update_fields=["telegram_id"])
    # deliberately no Bot row created for this tenant

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.bot.tasks.build_client", return_value=fake_bot):
        _notify_transaction_sync(txn.pk)  # must not raise

    assert fake_bot.sent == []


@pytest.mark.django_db
def test_register_webhook_calls_set_webhook_with_the_correct_url(settings, make_tenant):
    settings.PUBLIC_BASE_URL = "https://bots.example.com"
    tenant = make_tenant("t")
    bot_row = _make_bot_row(tenant)

    fake_bot = _FakeAiogramBot()
    with patch("apps.bot.tasks.build_client", return_value=fake_bot):
        _register_webhook_sync(bot_row)

    assert fake_bot.webhooks_set == [f"https://bots.example.com/webhook/{bot_row.webhook_secret}/"]


@pytest.mark.django_db
def test_register_webhook_skips_a_bot_with_no_token(make_tenant):
    tenant = make_tenant("t")
    bot_row = Bot.objects.all_tenants().create(tenant=tenant, username="@testbot")

    with patch("apps.bot.tasks.build_client") as mock_build:
        _register_webhook_sync(bot_row)

    mock_build.assert_not_called()


@pytest.mark.django_db
def test_rotate_bot_credentials_deregisters_the_old_webhook_and_refreshes_username(make_tenant):
    """Reproduces the reported bug: after rotating a bot's token, messaging
    the OLD bot was still getting answered (because its webhook, registered
    to the same URL, was never cleared) and the stored username never
    updated to match the new token's real identity."""
    tenant = make_tenant("t")
    bot_row = _make_bot_row(tenant)  # username="@testbot"

    old_bot = _FakeAiogramBot()
    new_bot = _FakeAiogramBot(username="brand_new_bot")

    with (
        patch("apps.bot.tasks.build_client_from_token", return_value=old_bot) as mock_from_token,
        patch("apps.bot.tasks.build_client", return_value=new_bot),
    ):
        _rotate_bot_credentials_sync(bot_row.pk, "OLD-TOKEN-VALUE")

    mock_from_token.assert_called_once_with("OLD-TOKEN-VALUE")
    assert old_bot.webhook_deleted is True
    bot_row.refresh_from_db()
    assert bot_row.username == "brand_new_bot"


@pytest.mark.django_db
def test_rotate_bot_credentials_tolerates_an_already_revoked_old_token(make_tenant):
    tenant = make_tenant("t")
    bot_row = _make_bot_row(tenant)

    class _RaisingOldBot(_FakeAiogramBot):
        async def delete_webhook(self):
            raise TelegramAPIError(method=None, message="Unauthorized")

    new_bot = _FakeAiogramBot(username="testbot")
    with (
        patch("apps.bot.tasks.build_client_from_token", return_value=_RaisingOldBot()),
        patch("apps.bot.tasks.build_client", return_value=new_bot),
    ):
        _rotate_bot_credentials_sync(bot_row.pk, "REVOKED-TOKEN")  # must not raise

    bot_row.refresh_from_db()
    assert bot_row.username == "testbot"


@pytest.mark.django_db
def test_sync_bot_display_name_calls_set_my_name(make_tenant):
    tenant = make_tenant("t")
    bot_row = _make_bot_row(tenant)

    fake_bot = _FakeAiogramBot()
    with patch("apps.bot.tasks.build_client", return_value=fake_bot):
        _sync_bot_display_name_sync(bot_row.pk, "Yangi Dorixona Nomi")

    assert fake_bot.names_set == ["Yangi Dorixona Nomi"]


@pytest.mark.django_db
def test_sync_bot_display_name_truncates_to_64_chars(make_tenant):
    tenant = make_tenant("t")
    bot_row = _make_bot_row(tenant)
    long_name = "A" * 200

    fake_bot = _FakeAiogramBot()
    with patch("apps.bot.tasks.build_client", return_value=fake_bot):
        _sync_bot_display_name_sync(bot_row.pk, long_name)

    assert fake_bot.names_set == ["A" * 64]


@pytest.mark.django_db
def test_sync_bot_display_name_is_a_noop_when_the_tenant_has_no_bot(make_tenant):
    make_tenant("t")  # no Bot row created

    with patch("apps.bot.tasks.build_client") as mock_build:
        _sync_bot_display_name_sync(999999, "Some Name")  # must not raise

    mock_build.assert_not_called()


@pytest.mark.django_db
def test_sync_bot_display_name_tolerates_telegram_errors(make_tenant):
    tenant = make_tenant("t")
    bot_row = _make_bot_row(tenant)

    class _RaisingBot(_FakeAiogramBot):
        async def set_my_name(self, name=None):
            raise TelegramAPIError(method=None, message="Unauthorized")

    with patch("apps.bot.tasks.build_client", return_value=_RaisingBot()):
        _sync_bot_display_name_sync(bot_row.pk, "New Name")  # must not raise
