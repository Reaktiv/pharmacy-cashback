import base64
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from apps.bot.qr import extract_url_from_photo, is_trusted_check_url
from apps.bot.services import handle_receipt_check_data
from apps.bot.tasks import _process_receipt_photo_sync
from apps.ledger.models import Transaction
from apps.tenants.models import Bot

# A real QR code encoding https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3,
# generated once with the `qrcode` package (deliberately not a project
# dependency — this fixture is the only place a QR encoder was ever
# needed), so extract_url_from_photo has a genuine positive case to
# decode, not just "garbage in, None out".
SAMPLE_QR_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAIQAAACEAQAAAAB5P74KAAABEElEQVR4nMWWQWoEMQwES8PcWz/Y"
    "/z9rftB+QecwG0g2BBIZEp1sgRpUsiRX+Gzr4NX+1lNV3c1aTVX1UIcoUXB0Hz3TOaEEoZfv406m"
    "3evS47dRXz3Lk6iPdkJolfCCMOVcKdDzskDXtF5JIidGSTKsF1EEkhxgXHdikQQigKnOgaCqDTbK"
    "tF5EJiaGBM/zyntrxIk3ONuJbd/A5zrKU0y2NvKyIgdLyQYfYRQBO3xOSIXGiMI97wtZdpBi7fGx"
    "IwGa8zkp0uAmtWr8ng8SDOvSumlP8wJEbJDY4KNEjuQo2ukLJBn5vs3fD3A9UqTy06hvPVfRbVZt"
    "zJ97nxrYmD8Hq4q2UFjG473z4vjnf8sb/g/Lm3wiRdIAAAAASUVORK5CYII="
)


def test_extract_url_from_photo_decodes_a_real_qr_code():
    assert extract_url_from_photo(SAMPLE_QR_PNG) == "https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3"


def test_extract_url_from_photo_returns_none_for_an_image_with_no_qr_code():
    # A valid, minimal 1x1 PNG (same fixture style as
    # apps/accounts/tests/test_me_api.py's TINY_PNG_BYTES) — a real image,
    # just not one that contains a QR code.
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
        "AAAAASUVORK5CYII="
    )
    assert extract_url_from_photo(tiny_png) is None


def test_extract_url_from_photo_returns_none_for_non_image_bytes():
    assert extract_url_from_photo(b"not an image at all") is None


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3", True),
        ("http://ofd.soliq.uz/check?t=X", False),  # wrong scheme
        ("https://evil.example.com/check?t=X", False),  # wrong host
        ("https://ofd.soliq.uz.evil.com/check?t=X", False),  # lookalike host
        ("https://ofd.soliq.uz/other-page", False),  # wrong path
        ("not a url", False),
    ],
)
def test_is_trusted_check_url(url, expected):
    assert is_trusted_check_url(url) is expected


def _check_data(
    tin=301422146, cash_total=0.0, card_total=10000.0, terminal_id="LG1", payment_no="119494"
):
    return {
        "tin": tin,
        "cash_total": cash_total,
        "card_total": card_total,
        "terminal_id": terminal_id,
        "payment_no": payment_no,
    }


@pytest.mark.django_db
def test_handle_receipt_check_data_rejects_an_unconfigured_tenant(make_tenant, make_customer):
    tenant = make_tenant("t", rate=Decimal("5.00"))  # receipt_tin left blank
    customer = make_customer(tenant)

    message = handle_receipt_check_data(tenant=tenant, customer=customer, check_data=_check_data())

    assert message is not None
    assert not Transaction.objects.all_tenants().filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_handle_receipt_check_data_rejects_a_tin_mismatch(make_tenant, make_branch, make_customer):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = make_branch(tenant)
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)

    message = handle_receipt_check_data(
        tenant=tenant, customer=customer, check_data=_check_data(tin=999999999)
    )

    assert message is not None
    assert not Transaction.objects.all_tenants().filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_handle_receipt_check_data_credits_cashback_on_a_matching_receipt(
    make_tenant, make_branch, make_customer
):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = branch
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)

    message = handle_receipt_check_data(
        tenant=tenant,
        customer=customer,
        check_data=_check_data(cash_total=0.0, card_total=10000.0),
    )

    assert message is None  # success — notify_transaction handles the reply
    txn = Transaction.objects.all_tenants().get(tenant=tenant, customer=customer)
    assert txn.branch_id == branch.id
    assert txn.seller_id is None
    assert txn.check_amount == Decimal("10000.00")
    assert txn.cashback_earned == Decimal("500.00")  # 5% of 10000


@pytest.mark.django_db
def test_handle_receipt_check_data_is_idempotent_on_the_same_receipt(
    make_tenant, make_branch, make_customer
):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = branch
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)
    check_data = _check_data()

    first = handle_receipt_check_data(tenant=tenant, customer=customer, check_data=check_data)
    second = handle_receipt_check_data(tenant=tenant, customer=customer, check_data=check_data)

    assert first is None
    assert second is not None  # "already used" rejection
    assert Transaction.objects.all_tenants().filter(tenant=tenant, customer=customer).count() == 1


class _FakeAiogramBot:
    def __init__(self):
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text})


def _make_bot_row(tenant):
    bot_row = Bot.objects.all_tenants().create(tenant=tenant, username="@testbot")
    bot_row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    bot_row.save()
    return bot_row


@pytest.mark.django_db
def test_process_receipt_photo_credits_cashback_and_sends_no_extra_message_on_success(
    make_tenant, make_branch, make_customer
):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = branch
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)
    customer.telegram_id = 555
    customer.save(update_fields=["telegram_id"])
    bot_row = _make_bot_row(tenant)

    fake_bot = _FakeAiogramBot()
    fetch = AsyncMock(return_value=_check_data())
    with (
        patch("apps.bot.tasks._fetch_receipt_via_playwright", fetch),
        patch("apps.bot.tasks.build_client", return_value=fake_bot),
    ):
        _process_receipt_photo_sync(
            tenant_id=tenant.id,
            customer_id=customer.id,
            chat_id=555,
            bot_id=bot_row.id,
            check_url="https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3",
        )

    fetch.assert_awaited_once_with("https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3")
    assert Transaction.objects.all_tenants().filter(tenant=tenant, customer=customer).exists()
    # The task itself sends nothing on success — post_earn_transaction's
    # own on_commit hook (notify_transaction) is what messages the
    # customer, and that Celery task isn't fired synchronously in tests.
    assert fake_bot.sent == []


@pytest.mark.django_db
def test_process_receipt_photo_notifies_the_customer_when_the_tin_does_not_match(
    make_tenant, make_branch, make_customer
):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = branch
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)
    customer.telegram_id = 555
    customer.save(update_fields=["telegram_id"])
    bot_row = _make_bot_row(tenant)

    fake_bot = _FakeAiogramBot()
    fetch = AsyncMock(return_value=_check_data(tin=999999999))
    with (
        patch("apps.bot.tasks._fetch_receipt_via_playwright", fetch),
        patch("apps.bot.tasks.build_client", return_value=fake_bot),
    ):
        _process_receipt_photo_sync(
            tenant_id=tenant.id,
            customer_id=customer.id,
            chat_id=555,
            bot_id=bot_row.id,
            check_url="https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3",
        )

    assert not Transaction.objects.all_tenants().filter(tenant=tenant, customer=customer).exists()
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["chat_id"] == 555


@pytest.mark.django_db
def test_process_receipt_photo_notifies_the_customer_when_the_fetch_fails(
    make_tenant, make_branch, make_customer
):
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = branch
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)
    customer.telegram_id = 555
    customer.save(update_fields=["telegram_id"])
    bot_row = _make_bot_row(tenant)

    fake_bot = _FakeAiogramBot()
    fetch = AsyncMock(return_value=None)  # e.g. a malformed/expired check URL
    with (
        patch("apps.bot.tasks._fetch_receipt_via_playwright", fetch),
        patch("apps.bot.tasks.build_client", return_value=fake_bot),
    ):
        _process_receipt_photo_sync(
            tenant_id=tenant.id,
            customer_id=customer.id,
            chat_id=555,
            bot_id=bot_row.id,
            check_url="https://ofd.soliq.uz/check?t=X&r=1&c=2&s=3",
        )

    assert not Transaction.objects.all_tenants().filter(tenant=tenant, customer=customer).exists()
    assert len(fake_bot.sent) == 1


@pytest.mark.django_db
def test_process_receipt_photo_refuses_an_untrusted_check_url(
    make_tenant, make_branch, make_customer
):
    """Defense in depth (apps.bot.handlers.on_receipt_photo already checks
    this before ever queuing the task) — the task must not launch
    Playwright against a URL that isn't ofd.soliq.uz's own check page."""
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    tenant.receipt_tin = "301422146"
    tenant.receipt_branch = branch
    tenant.save(update_fields=["receipt_tin", "receipt_branch"])
    customer = make_customer(tenant)
    bot_row = _make_bot_row(tenant)

    fetch = AsyncMock(return_value=_check_data())
    with patch("apps.bot.tasks._fetch_receipt_via_playwright", fetch):
        _process_receipt_photo_sync(
            tenant_id=tenant.id,
            customer_id=customer.id,
            chat_id=555,
            bot_id=bot_row.id,
            check_url="https://evil.example.com/check?t=X",
        )

    fetch.assert_not_awaited()
