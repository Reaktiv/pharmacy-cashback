from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from apps.broadcasts.models import Broadcast, BroadcastDeliveryLog, BroadcastMedia
from apps.broadcasts.tasks import send_broadcast
from apps.customers.models import Customer
from apps.tenants.models import Bot as BotRow


def _make_bot_row(tenant):
    bot_row = BotRow.objects.all_tenants().create(tenant=tenant, username="@testbot")
    bot_row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    bot_row.save()
    return bot_row


def _make_media(tenant, admin, media_type=BroadcastMedia.MediaType.IMAGE):
    return BroadcastMedia.objects.all_tenants().create(
        tenant=tenant,
        file=f"broadcast_media/{tenant.id}/fake.jpg",
        media_type=media_type,
        original_filename="fake.jpg",
        content_type="image/jpeg" if media_type == BroadcastMedia.MediaType.IMAGE else "video/mp4",
        size_bytes=1234,
        uploaded_by=admin,
    )


class _FakeAiogramBot:
    """Mimics just enough of aiogram's Bot surface for send_broadcast:
    send_message/send_photo/send_video, each of which can be told to raise
    TelegramForbiddenError, TelegramRetryAfter (N times before succeeding),
    or a generic error for a given chat_id."""

    def __init__(self, forbidden_for=None, retry_after_for=None, error_for=None):
        self.sent = []
        self.forbidden_for = forbidden_for or set()
        self.retry_after_for = {k: list(v) for k, v in (retry_after_for or {}).items()}
        self.error_for = error_for or set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _dispatch(self, chat_id, kind, **payload):
        if chat_id in self.forbidden_for:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        if chat_id in self.error_for:
            raise RuntimeError("something else went wrong")
        pending = self.retry_after_for.get(chat_id)
        if pending:
            wait = pending.pop(0)
            raise TelegramRetryAfter(method=None, message="Too Many Requests", retry_after=wait)
        self.sent.append({"chat_id": chat_id, "kind": kind, **payload})

    async def send_message(self, chat_id, text, parse_mode=None, **kwargs):
        await self._dispatch(chat_id, "text", text=text)

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, **kwargs):
        await self._dispatch(chat_id, "photo", caption=caption)

    async def send_video(self, chat_id, video, caption=None, parse_mode=None, **kwargs):
        await self._dispatch(chat_id, "video", caption=caption)


@pytest.mark.django_db
def test_send_broadcast_reaches_all_registered_active_customers(make_tenant, make_user):
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
    assert broadcast.sent_at is not None
    assert {call["chat_id"] for call in fake_bot.sent} == {111, 222, 333}
    assert "Sale!" in fake_bot.sent[0]["text"]

    logs = BroadcastDeliveryLog.objects.all_tenants().filter(broadcast=broadcast)
    assert logs.count() == 3
    assert all(log.status == BroadcastDeliveryLog.Status.SUCCESS for log in logs)


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

    blocked_log = BroadcastDeliveryLog.objects.all_tenants().get(
        broadcast=broadcast, customer=blocked_customer
    )
    assert blocked_log.status == BroadcastDeliveryLog.Status.BLOCKED
    assert blocked_log.error_detail


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


@pytest.mark.django_db
def test_send_broadcast_skips_cleanly_when_the_broadcast_no_longer_exists():
    # Regression test: a Broadcast deleted after send_broadcast.delay() was
    # queued (e.g. via Django admin, since apps.broadcasts.api_views.
    # BroadcastViewSet.perform_destroy only blocks the ordinary API path)
    # used to raise Broadcast.DoesNotExist straight out of this task,
    # showing up as an unhandled Celery error instead of a clean no-op.
    send_broadcast(999999)  # must not raise


@pytest.mark.django_db
def test_send_broadcast_sends_photo_when_image_media_attached(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    media = _make_media(tenant, admin, media_type=BroadcastMedia.MediaType.IMAGE)
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="<b>20% off</b>", media=media, created_by=admin
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.broadcasts.tasks.build_client", return_value=fake_bot):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.sent_count == 1
    assert fake_bot.sent == [
        {"chat_id": 111, "kind": "photo", "caption": "<b>Sale!</b>\n\n<b>20% off</b>"}
    ]


@pytest.mark.django_db
def test_send_broadcast_sends_video_when_video_media_attached(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    media = _make_media(tenant, admin, media_type=BroadcastMedia.MediaType.VIDEO)
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", media=media, created_by=admin
    )

    fake_bot = _FakeAiogramBot()
    with patch("apps.broadcasts.tasks.build_client", return_value=fake_bot):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.sent_count == 1
    assert fake_bot.sent[0]["kind"] == "video"


@pytest.mark.django_db
def test_send_broadcast_respects_retry_after_and_eventually_succeeds(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    # Fails with flood control twice, then succeeds on the third attempt —
    # comfortably inside MAX_ATTEMPTS.
    fake_bot = _FakeAiogramBot(retry_after_for={111: [2, 3]})
    with (
        patch("apps.broadcasts.tasks.build_client", return_value=fake_bot),
        patch("apps.broadcasts.tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.status == Broadcast.Status.SENT
    assert broadcast.sent_count == 1
    assert broadcast.failed_count == 0
    assert {call["chat_id"] for call in fake_bot.sent} == {111}

    # The two retry_after waits were actually respected (not ignored/skipped).
    slept_for = [call.args[0] for call in mock_sleep.call_args_list]
    assert slept_for[0] == 2
    assert slept_for[1] == 3


@pytest.mark.django_db
def test_send_broadcast_gives_up_after_max_retry_after_attempts(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    # Always floods — more retry_after values than MAX_ATTEMPTS allows.
    fake_bot = _FakeAiogramBot(retry_after_for={111: [1, 1, 1, 1, 1, 1]})
    with (
        patch("apps.broadcasts.tasks.build_client", return_value=fake_bot),
        patch("apps.broadcasts.tasks.asyncio.sleep", new=AsyncMock()),
    ):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.status == Broadcast.Status.SENT  # the run itself completed
    assert broadcast.sent_count == 0
    assert broadcast.failed_count == 1

    log = BroadcastDeliveryLog.objects.all_tenants().get(broadcast=broadcast)
    assert log.status == BroadcastDeliveryLog.Status.FAILED
    assert "Flood control" in log.error_detail


@pytest.mark.django_db
def test_send_broadcast_classifies_generic_errors_as_failed(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    fake_bot = _FakeAiogramBot(error_for={111})
    with patch("apps.broadcasts.tasks.build_client", return_value=fake_bot):
        send_broadcast(broadcast.pk)

    broadcast.refresh_from_db()
    assert broadcast.failed_count == 1
    log = BroadcastDeliveryLog.objects.all_tenants().get(broadcast=broadcast)
    assert log.status == BroadcastDeliveryLog.Status.FAILED
    assert "something else went wrong" in log.error_detail


@pytest.mark.django_db
def test_send_broadcast_marks_failed_when_the_task_itself_crashes(make_tenant, make_user):
    tenant = make_tenant("t")
    _make_bot_row(tenant)
    admin = make_user()
    Customer.objects.all_tenants().create(
        tenant=tenant, phone="+998900000001", telegram_id=111, is_active=True
    )
    broadcast = Broadcast.objects.all_tenants().create(
        tenant=tenant, title="Sale!", body="body", created_by=admin
    )

    with patch("apps.broadcasts.tasks.build_client", side_effect=RuntimeError("boom")):
        send_broadcast(broadcast.pk)  # must not raise

    broadcast.refresh_from_db()
    assert broadcast.status == Broadcast.Status.FAILED
