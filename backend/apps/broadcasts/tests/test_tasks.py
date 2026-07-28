from unittest.mock import patch

import pytest
from aiogram.exceptions import TelegramForbiddenError

from apps.broadcasts.models import Broadcast
from apps.broadcasts.tasks import send_broadcast
from apps.customers.models import Customer
from apps.tenants.models import Bot as BotRow


def _make_bot_row(tenant):
    bot_row = BotRow.objects.all_tenants().create(tenant=tenant, username="@testbot")
    bot_row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    bot_row.save()
    return bot_row


class _FakeAiogramBot:
    def __init__(self, forbidden_for=None):
        self.sent = []
        self.forbidden_for = forbidden_for or set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, chat_id, text, reply_markup=None):
        if chat_id in self.forbidden_for:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        self.sent.append({"chat_id": chat_id, "text": text})


@pytest.mark.django_db
def test_send_broadcast_reaches_all_registered_active_customers(
    make_tenant, make_user
):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    for i, tg_id in enumerate([111, 222, 333]):
        Customer.objects.all_tenants().create(
            tenant=tenant, phone=f"+99890000000{i}", telegram_id=tg_id, is_active=True
        )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="20% off today.", created_by=admin
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.broadcasts.tasks.build_client", return_value=fake_bot):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.status == Broadcast.Status.SENT
    assert broadcast.sent_count == 3
    assert broadcast.failed_count == 0
    assert {call["chat_id"] for call in fake_bot.sent} == {111, 222, 333}
    assert "Sale!" in fake_bot.sent[0]["text"]


@pytest.mark.django_db
def test_send_broadcast_skips_unregistered_and_inactive_customers(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=None
    )  # not registered
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000002", telegram_id=222, is_active=False
    )  # inactive
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000003", telegram_id=333, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.broadcasts.tasks.build_client", return_value=fake_bot):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.sent_count == 1
    assert {call["chat_id"] for call in fake_bot.sent} == {333}


@pytest.mark.django_db
def test_send_broadcast_handles_blocked_customers_without_crashing(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000002", telegram_id=222, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    fake_bot = _FakeAiogramBot(forbidden_for={111})
    with patch("apps.broadcasts.tasks.build_client", return_value=fake_bot):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.status == Broadcast.Status.SENT
    assert broadcast.sent_count == 1
    assert broadcast.failed_count == 1

    blocked_customer = Customer.objects.all_tenants().get(telegram_id=111)
    assert blocked_customer.is_active is False  # deactivated so future broadcasts skip them
    still_active = Customer.objects.all_tenants().get(telegram_id=222)
    assert still_active.is_active is True


@pytest.mark.django_db
def test_send_broadcast_aborts_cleanly_when_tenant_has_no_bot(make_tenant, make_user):
    tenant = make_tenant("t")
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    send_broadcast(broadcast.pk)  # must not raise

    broadcast.refresh_from_db()
    assert broadcast.status == Broadcast.Status.DRAFT  # never even started
