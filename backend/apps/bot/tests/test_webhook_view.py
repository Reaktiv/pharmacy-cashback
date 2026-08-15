"""End-to-end webhook tests: real Django test client -> real async webhook
view -> real aiogram Dispatcher -> real handlers -> real Django ORM. Only
the actual outbound Telegram HTTP calls are mocked, via patching
aiogram.Bot.__call__ (the single choke point every API call funnels
through) — the webhook view still builds a genuine aiogram.Bot instance, so
this exercises the real aiogram plumbing, not a stand-in.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from aiogram import Bot as AiogramBot

from apps.customers.models import OTP, Customer
from apps.ledger.services import get_balance, post_earn_by_phone, post_earn_transaction
from apps.tenants.models import Bot as BotRow


@pytest.fixture
def bot_row(make_tenant, make_branch, make_seller):
    tenant = make_tenant("botshop", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    row = BotRow.objects.all_tenants().create(tenant=tenant, username="@botshop_bot")
    row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    row.save()
    return {"row": row, "tenant": tenant, "branch": branch, "seller": seller}


@pytest.fixture(autouse=True)
def mock_outbound_telegram():
    """Every aiogram Bot API call — however it's invoked (message.answer(),
    callback.answer(), bot.send_message(), ...) — funnels through
    Bot.__call__(method_object). Patching there is the one interception
    point that reliably covers all of them, rather than guessing which
    convenience methods handlers happen to use.
    """
    calls = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return None

    with patch.object(AiogramBot, "__call__", new=fake_call):
        yield calls


def _sent_texts(calls):
    return [call.text for call in calls if call.__class__.__name__ == "SendMessage"]


def _webhook_url(row):
    return f"/webhook/{row.webhook_secret}/"


def _update(update_id, **fields):
    return {"update_id": update_id, **fields}


def _callback_update(update_id, chat_id, user_id, data, first_name="Aziz"):
    return _update(
        update_id,
        callback_query={
            "id": f"cbq{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": first_name},
            "chat_instance": "abc",
            "data": data,
            "message": {
                "message_id": update_id,
                "date": 1234567890,
                "chat": {"id": chat_id, "type": "private"},
                "from": {"id": 999999, "is_bot": True, "first_name": "Bot"},
                "text": "placeholder",
            },
        },
    )


def _message_update(update_id, chat_id, user_id, **extra):
    return _update(
        update_id,
        message={
            "message_id": update_id,
            "date": 1234567890,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Aziz"},
            **extra,
        },
    )


@pytest.mark.django_db
def test_unknown_webhook_secret_returns_404(client):
    response = client.post("/webhook/does-not-exist/", data={}, content_type="application/json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_start_command_sends_the_language_picker_for_a_new_user(
    client, bot_row, mock_outbound_telegram
):
    payload = _message_update(
        1,
        chat_id=111,
        user_id=111,
        text="/start",
        entities=[{"type": "bot_command", "offset": 0, "length": 6}],
    )

    response = client.post(
        _webhook_url(bot_row["row"]), data=payload, content_type="application/json"
    )

    assert response.status_code == 200
    sent = [c for c in mock_outbound_telegram if c.__class__.__name__ == "SendMessage"]
    assert len(sent) == 1
    codes = {btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row}
    assert codes == {"reglang:uz", "reglang:en", "reglang:ru"}


@pytest.mark.django_db
def test_picking_a_language_sends_the_contact_request_keyboard_in_that_language(
    client, bot_row, mock_outbound_telegram
):
    client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=111, user_id=111, text="/start"),
        content_type="application/json",
    )

    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_callback_update(2, chat_id=111, user_id=111, data="reglang:en"),
        content_type="application/json",
    )

    assert response.status_code == 200
    sent = [c for c in mock_outbound_telegram if c.__class__.__name__ == "SendMessage"]
    assert len(sent) == 2  # the language picker, then this contact-request keyboard
    assert sent[-1].reply_markup.keyboard[0][0].request_contact is True
    assert sent[-1].reply_markup.keyboard[0][0].text == "Share my phone number"
    assert "Welcome to" in sent[-1].text


@pytest.mark.django_db
def test_start_command_greets_an_already_registered_customer_without_asking_again(
    client, bot_row, mock_outbound_telegram, make_customer
):
    tenant = bot_row["tenant"]
    customer = make_customer(tenant, phone="+998900000005")
    customer.telegram_id = 555
    customer.save(update_fields=["telegram_id"])

    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=555, user_id=555, text="/start"),
        content_type="application/json",
    )

    assert response.status_code == 200
    sent = [c for c in mock_outbound_telegram if c.__class__.__name__ == "SendMessage"]
    assert len(sent) == 1
    assert "Qaytib kelganingizdan xursandmiz" in sent[0].text
    assert sent[0].reply_markup.keyboard[0][0].request_contact is not True


@pytest.mark.django_db
def test_full_registration_flow_registers_customer_and_claims_pending_cashback(
    client, bot_row, mock_outbound_telegram
):
    tenant = bot_row["tenant"]
    branch = bot_row["branch"]
    seller = bot_row["seller"]

    # A sale happened before this customer ever opened the bot.
    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998901234567",
        check_amount=Decimal("100000"),
        idempotency_key="pre-reg",
    )

    # /start
    client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=111, user_id=111, text="/start"),
        content_type="application/json",
    )

    # pick a language
    client.post(
        _webhook_url(bot_row["row"]),
        data=_callback_update(2, chat_id=111, user_id=111, data="reglang:uz"),
        content_type="application/json",
    )

    # share contact
    contact_update = _message_update(
        3,
        chat_id=111,
        user_id=111,
        contact={"phone_number": "998901234567", "first_name": "Aziz", "user_id": 111},
    )
    response = client.post(
        _webhook_url(bot_row["row"]), data=contact_update, content_type="application/json"
    )
    assert response.status_code == 200

    # tap "I agree"
    consent_update = _callback_update(4, chat_id=111, user_id=111, data="consent:accept")
    response = client.post(
        _webhook_url(bot_row["row"]), data=consent_update, content_type="application/json"
    )
    assert response.status_code == 200

    customer = Customer.objects.all_tenants().get(tenant=tenant, phone="+998901234567")
    assert customer.telegram_id == 111
    assert customer.consent_given_at is not None
    assert customer.language == "uz"
    assert get_balance(customer) == Decimal("10000.00")  # the pre-registration sale, claimed

    # the registration confirmation should mention the claimed amount + balance
    texts = _sent_texts(mock_outbound_telegram)
    assert "10000.00" in texts[-1]


@pytest.mark.django_db
def test_balance_button_reports_current_balance(
    client, bot_row, mock_outbound_telegram, make_customer
):
    tenant = bot_row["tenant"]
    customer = make_customer(tenant, phone="+998900000002")
    customer.telegram_id = 222
    customer.save(update_fields=["telegram_id"])

    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=222, user_id=222, text="💰 Balans"),
        content_type="application/json",
    )

    assert response.status_code == 200
    texts = _sent_texts(mock_outbound_telegram)
    assert "Balansingiz: 0" in texts[-1]


@pytest.mark.django_db
def test_redeem_flow_issues_an_otp(client, bot_row, mock_outbound_telegram, make_customer):
    tenant = bot_row["tenant"]
    branch = bot_row["branch"]
    seller = bot_row["seller"]
    customer = make_customer(tenant, phone="+998900000003")
    customer.telegram_id = 333
    customer.save(update_fields=["telegram_id"])
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="seed",
    )

    # tap "Redeem"
    client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=333, user_id=333, text="🎟 Ballarni ishlatish"),
        content_type="application/json",
    )
    # send the amount
    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(2, chat_id=333, user_id=333, text="20000"),
        content_type="application/json",
    )

    assert response.status_code == 200
    otp = OTP.objects.all_tenants().get(tenant=tenant, customer=customer)
    assert otp.amount_requested == Decimal("20000")
    texts = _sent_texts(mock_outbound_telegram)
    assert "Sizning kodingiz:" in texts[-1]
    assert otp.code in texts[-1]


@pytest.mark.django_db
def test_cancel_button_clears_an_in_progress_redeem_flow(
    client, bot_row, mock_outbound_telegram, make_customer
):
    tenant = bot_row["tenant"]
    customer = make_customer(tenant, phone="+998900000010")
    customer.telegram_id = 1010
    customer.save(update_fields=["telegram_id"])

    # tap "Redeem" — this sets RedeemStates.awaiting_amount
    client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=1010, user_id=1010, text="🎟 Ballarni ishlatish"),
        content_type="application/json",
    )
    # tap "Cancel" instead of sending an amount
    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(2, chat_id=1010, user_id=1010, text="❌ Bekor qilish"),
        content_type="application/json",
    )
    assert response.status_code == 200
    texts = _sent_texts(mock_outbound_telegram)
    assert texts[-1] == "Bekor qilindi."

    # the cleared state must mean a plain number is no longer interpreted
    # as a redeem amount — sending one now must not create an OTP.
    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(3, chat_id=1010, user_id=1010, text="20000"),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert not OTP.objects.all_tenants().filter(tenant=tenant, customer=customer).exists()


@pytest.mark.django_db
def test_report_button_flags_the_transaction(
    client, bot_row, mock_outbound_telegram, make_customer
):
    from apps.ledger.models import Transaction

    tenant = bot_row["tenant"]
    branch = bot_row["branch"]
    seller = bot_row["seller"]
    customer = make_customer(tenant, phone="+998900000004")
    customer.telegram_id = 444
    customer.save(update_fields=["telegram_id"])
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    callback_update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq1",
            "from": {"id": 444, "is_bot": False, "first_name": "Aziz"},
            "chat_instance": "abc",
            "data": f"report:{txn.pk}",
            "message": {
                "message_id": 1,
                "date": 1234567890,
                "chat": {"id": 444, "type": "private"},
                "from": {"id": 999999, "is_bot": True, "first_name": "Bot"},
                "text": "notification",
            },
        },
    }

    response = client.post(
        _webhook_url(bot_row["row"]), data=callback_update, content_type="application/json"
    )

    assert response.status_code == 200
    assert Transaction.objects.all_tenants().get(pk=txn.pk).flagged is True


@pytest.mark.django_db
def test_settings_button_shows_the_settings_menu(
    client, bot_row, mock_outbound_telegram, make_customer
):
    tenant = bot_row["tenant"]
    customer = make_customer(tenant, phone="+998900000006")
    customer.telegram_id = 666
    customer.save(update_fields=["telegram_id"])

    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(1, chat_id=666, user_id=666, text="⚙️ Sozlamalar"),
        content_type="application/json",
    )

    assert response.status_code == 200
    sent = [c for c in mock_outbound_telegram if c.__class__.__name__ == "SendMessage"]
    assert len(sent) == 1
    codes = {btn.callback_data for row in sent[0].reply_markup.inline_keyboard for btn in row}
    assert codes == {"settings:name", "settings:language"}


@pytest.mark.django_db
def test_settings_change_name_flow_updates_the_customers_full_name(
    client, bot_row, mock_outbound_telegram, make_customer
):
    tenant = bot_row["tenant"]
    customer = make_customer(tenant, phone="+998900000007")
    customer.telegram_id = 777
    customer.save(update_fields=["telegram_id"])

    client.post(
        _webhook_url(bot_row["row"]),
        data=_callback_update(1, chat_id=777, user_id=777, data="settings:name"),
        content_type="application/json",
    )
    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_message_update(2, chat_id=777, user_id=777, text="Yangi Ism"),
        content_type="application/json",
    )

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.full_name == "Yangi Ism"
    texts = _sent_texts(mock_outbound_telegram)
    assert "Yangi Ism" in texts[-1]


@pytest.mark.django_db
def test_settings_change_language_flow_updates_the_customers_language_and_replies_in_it(
    client, bot_row, mock_outbound_telegram, make_customer
):
    tenant = bot_row["tenant"]
    customer = make_customer(tenant, phone="+998900000008")
    customer.telegram_id = 888
    customer.save(update_fields=["telegram_id"])
    assert customer.language == "uz"

    client.post(
        _webhook_url(bot_row["row"]),
        data=_callback_update(1, chat_id=888, user_id=888, data="settings:language"),
        content_type="application/json",
    )
    response = client.post(
        _webhook_url(bot_row["row"]),
        data=_callback_update(2, chat_id=888, user_id=888, data="setlang:ru"),
        content_type="application/json",
    )

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.language == "ru"
    texts = _sent_texts(mock_outbound_telegram)
    assert texts[-1] == "Язык изменён."


@pytest.mark.django_db
def test_notification_after_a_language_change_is_sent_in_the_new_language(
    bot_row, make_customer
):
    """Reproduces the exact scenario reported: a customer switches to
    Russian via Settings, then a later cashback notification (fired by
    apps.bot.tasks.notify_transaction, off apps.ledger.services'
    post_earn_transaction on_commit hook) must use that new language, not
    whatever it was at registration time."""
    from apps.bot.services import format_notification_text
    from apps.ledger.services import post_earn_transaction

    tenant = bot_row["tenant"]
    branch = bot_row["branch"]
    seller = bot_row["seller"]
    customer = make_customer(tenant, phone="+998900000009")
    customer.telegram_id = 999
    customer.language = "ru"
    customer.save(update_fields=["telegram_id", "language"])

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    text = format_notification_text(txn)

    assert "баллов" in text
    assert "qo'shildi" not in text
