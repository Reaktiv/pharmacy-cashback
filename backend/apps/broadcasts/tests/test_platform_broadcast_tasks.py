from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import UserProfile
from apps.broadcasts.models import (
    Broadcast,
    BroadcastMedia,
    PlatformBroadcast,
    PlatformBroadcastMedia,
)
from apps.broadcasts.tasks import send_platform_broadcast
from apps.tenants.models import Bot as BotRow


def _make_bot_row(tenant, is_active=True, token="123456:FAKE-TOKEN-FOR-TESTS"):
    bot_row = BotRow.objects.all_tenants().create(
        tenant=tenant, username=f"@bot{tenant.pk}", is_active=is_active
    )
    if token:
        bot_row.set_token(token)
    bot_row.save()
    return bot_row


@pytest.mark.django_db
def test_fan_out_creates_one_leg_per_active_tenant_with_a_bot(make_tenant, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    _make_bot_row(tenant_a)
    _make_bot_row(tenant_b)
    pb = PlatformBroadcast.objects.create(title="Announcement", body="Hello", created_by=superadmin)

    with patch("apps.broadcasts.tasks.send_broadcast") as mock_send:
        send_platform_broadcast(pb.pk)

    legs = Broadcast.objects.all_tenants().filter(platform_broadcast=pb)
    assert legs.count() == 2
    assert {leg.tenant_id for leg in legs} == {tenant_a.id, tenant_b.id}
    assert mock_send.delay.call_count == 2
    dispatched_pks = {call.args[0] for call in mock_send.delay.call_args_list}
    assert dispatched_pks == set(legs.values_list("pk", flat=True))

    pb.refresh_from_db()
    assert pb.status == PlatformBroadcast.Status.SENT
    assert pb.sent_at is not None


@pytest.mark.django_db
def test_fan_out_creates_legs_already_sending_never_draft(make_tenant, make_user):
    """Regression test for the double-send race: a DRAFT leg would be
    clickable via the owning tenant's own broadcast list before
    send_broadcast actually runs."""
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    tenant = make_tenant("a")
    _make_bot_row(tenant)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)

    with patch("apps.broadcasts.tasks.send_broadcast"):
        send_platform_broadcast(pb.pk)

    leg = Broadcast.objects.all_tenants().get(platform_broadcast=pb)
    assert leg.status == Broadcast.Status.SENDING


@pytest.mark.django_db
def test_fan_out_skips_inactive_tenants_and_tenants_without_a_bot(make_tenant, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    active_tenant = make_tenant("active")
    _make_bot_row(active_tenant)

    inactive_tenant = make_tenant("inactive")
    inactive_tenant.is_active = False
    inactive_tenant.save()
    _make_bot_row(inactive_tenant)

    make_tenant("nobot")

    inactive_bot_tenant = make_tenant("inactivebot")
    _make_bot_row(inactive_bot_tenant, is_active=False)

    no_token_tenant = make_tenant("notoken")
    _make_bot_row(no_token_tenant, token=None)

    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)

    with patch("apps.broadcasts.tasks.send_broadcast"):
        send_platform_broadcast(pb.pk)

    legs = Broadcast.objects.all_tenants().filter(platform_broadcast=pb)
    assert legs.count() == 1
    assert legs.first().tenant_id == active_tenant.id


@pytest.mark.django_db
def test_fan_out_copies_media_into_a_distinct_broadcast_media_row_per_tenant(
    make_tenant, make_user
):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    _make_bot_row(tenant_a)
    _make_bot_row(tenant_b)
    media = PlatformBroadcastMedia.objects.create(
        file=SimpleUploadedFile("pic.png", b"pixel-bytes", content_type="image/png"),
        media_type=PlatformBroadcastMedia.MediaType.IMAGE,
        original_filename="pic.png",
        content_type="image/png",
        size_bytes=11,
        uploaded_by=superadmin,
    )
    pb = PlatformBroadcast.objects.create(
        title="T", body="b", created_by=superadmin, media=media
    )

    with patch("apps.broadcasts.tasks.send_broadcast"):
        send_platform_broadcast(pb.pk)

    legs = list(
        Broadcast.objects.all_tenants().filter(platform_broadcast=pb).select_related("media")
    )
    assert len(legs) == 2
    media_rows = [leg.media for leg in legs]
    assert all(m is not None for m in media_rows)
    assert len({m.pk for m in media_rows}) == 2  # distinct rows, not shared
    assert {leg.tenant_id for leg in legs} == {tenant_a.id, tenant_b.id}
    for leg, m in zip(legs, media_rows, strict=True):
        assert m.tenant_id == leg.tenant_id
        assert m.original_filename == "pic.png"
        with m.file.open("rb") as fh:
            assert fh.read() == b"pixel-bytes"

    # The two copies are genuinely separate BroadcastMedia rows/files, not
    # the same one reused across tenants.
    media_pks = [m.pk for m in media_rows]
    assert BroadcastMedia.objects.all_tenants().filter(pk__in=media_pks).count() == 2


@pytest.mark.django_db
def test_fan_out_one_tenants_failure_does_not_block_the_others(make_tenant, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    _make_bot_row(tenant_a)
    _make_bot_row(tenant_b)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)

    real_queryset = Broadcast.objects.all_tenants()
    call_count = {"n": 0}

    class _FlakyQuerySet:
        def create(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated failure for the first tenant")
            return real_queryset.create(*args, **kwargs)

    with (
        patch("apps.broadcasts.tasks.send_broadcast") as mock_send,
        patch(
            "apps.broadcasts.tasks.Broadcast.objects.all_tenants",
            return_value=_FlakyQuerySet(),
        ),
    ):
        send_platform_broadcast(pb.pk)

    legs = real_queryset.filter(platform_broadcast=pb)
    assert legs.count() == 1
    assert mock_send.delay.call_count == 1

    pb.refresh_from_db()
    assert pb.status == PlatformBroadcast.Status.SENT  # partial success is still "dispatched"


@pytest.mark.django_db
def test_fan_out_marks_failed_when_nothing_could_be_dispatched(make_tenant, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    pb = PlatformBroadcast.objects.create(title="T", body="b", created_by=superadmin)
    # No tenants with an active bot at all.

    with patch("apps.broadcasts.tasks.send_broadcast") as mock_send:
        send_platform_broadcast(pb.pk)

    assert mock_send.delay.call_count == 0
    pb.refresh_from_db()
    assert pb.status == PlatformBroadcast.Status.FAILED
