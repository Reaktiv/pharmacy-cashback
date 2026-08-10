import os
import uuid

from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel


def broadcast_media_upload_path(instance: "BroadcastMedia", filename: str) -> str:
    """Tenant-scoped storage path. This alone is NOT the isolation
    boundary — see BroadcastMediaFileView, which is the only thing that
    ever reads these files back, and does so through the tenant-filtered
    `BroadcastMedia.objects` manager (CLAUDE.md §4)."""
    ext = os.path.splitext(filename)[1].lower()
    return f"broadcast_media/{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


class BroadcastMedia(TenantScopedModel):
    """One uploaded image/video, attached to at most one Broadcast. Kept as
    its own model (rather than a field on Broadcast) so upload can happen
    before the rest of the composer form is filled in/submitted."""

    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    file = models.FileField(upload_to=broadcast_media_upload_path)
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_filename


def platform_broadcast_media_upload_path(instance: "PlatformBroadcastMedia", filename: str) -> str:
    """Not tenant-scoped — this media is authored once by a superadmin before
    any tenant is chosen, then copied per-tenant into a real (tenant-scoped)
    BroadcastMedia row at fan-out time (see apps.broadcasts.tasks.
    send_platform_broadcast). This row itself is never sent to Telegram."""
    ext = os.path.splitext(filename)[1].lower()
    return f"platform_broadcast_media/{uuid.uuid4().hex}{ext}"


class PlatformBroadcastMedia(models.Model):
    """Superadmin-authored media for a platform-wide broadcast. Deliberately
    NOT a TenantScopedModel — TenantScopedModel.tenant is a required FK, and
    this media exists before any tenant is chosen (it fans out to all of
    them). See PlatformBroadcast."""

    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    file = models.FileField(upload_to=platform_broadcast_media_upload_path)
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_filename


class PlatformBroadcast(models.Model):
    """A superadmin broadcast fanned out to every active tenant's customers
    through that tenant's own bot (CLAUDE.md §7c superadmin dashboard).
    Deliberately not tenant-scoped, for the same reason as
    PlatformBroadcastMedia. Sending it creates one per-tenant `Broadcast` row
    per active, bot-configured tenant (see `Broadcast.platform_broadcast` and
    apps.broadcasts.tasks.send_platform_broadcast) and reuses the existing
    per-tenant `send_broadcast` task unchanged for actual delivery.

    No sent_count/failed_count/tenant_count columns here — those are derived
    from the child Broadcast rows (apps.broadcasts.api_views.
    PlatformBroadcastViewSet.get_queryset annotates them) rather than kept as
    a second, driftable source of truth.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    media = models.ForeignKey(
        PlatformBroadcastMedia,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_broadcasts",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Broadcast(TenantScopedModel):
    """CLAUDE.md §5. Pulled forward from Phase 8 into Phase 7, since Phase
    7's own done-criterion ("tenant admin ... sends a broadcast") requires
    it — see apps.broadcasts.tasks for the throttled Celery send.

    `body` holds sanitized Telegram-safe HTML (only the tags
    apps.broadcasts.sanitizer allows) — never raw editor output. FAILED is
    reserved for a broadcast whose send task crashed outright (see
    apps.broadcasts.tasks.send_broadcast); a tenant with no bot configured
    still just aborts back to DRAFT, unchanged from before.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    media = models.ForeignKey(
        BroadcastMedia,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="broadcasts",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    platform_broadcast = models.ForeignKey(
        PlatformBroadcast,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenant_legs",
        help_text="Set when this row is one tenant's leg of a superadmin "
        "platform-wide broadcast, fanned out by "
        "apps.broadcasts.tasks.send_platform_broadcast. Null for a normal "
        "tenant_admin-authored broadcast — also the marker used to exclude "
        "these from a tenant's monthly broadcast_quota count.",
    )

    def __str__(self):
        return self.title


class BroadcastDeliveryLog(TenantScopedModel):
    """Per-recipient delivery outcome for one broadcast send — lets a
    failure be classified as permanent (blocked) vs transient (failed),
    distinct from the aggregate sent_count/failed_count on Broadcast itself.

    PENDING_RETRY is in the schema for a future async-requeue design; the
    current send_broadcast task resolves Telegram's flood-control retries
    in-process (sleep + retry within the same task run) before ever writing
    a row, so only terminal statuses (success/blocked/failed) are written
    today.
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        BLOCKED = "blocked", "Bot Blocked"
        FAILED = "failed", "Failed"
        PENDING_RETRY = "pending_retry", "Pending Retry"

    broadcast = models.ForeignKey(
        Broadcast, on_delete=models.CASCADE, related_name="delivery_logs"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="broadcast_delivery_logs"
    )
    status = models.CharField(max_length=15, choices=Status.choices)
    error_detail = models.TextField(blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.broadcast_id}:{self.customer_id}:{self.status}"
