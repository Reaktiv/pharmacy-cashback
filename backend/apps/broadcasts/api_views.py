from urllib.parse import quote

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsSuperadmin, IsTenantAdmin
from apps.audit.services import log_action
from apps.broadcasts.models import (
    Broadcast,
    BroadcastMedia,
    PlatformBroadcast,
    PlatformBroadcastMedia,
)
from apps.broadcasts.serializers import (
    BroadcastMediaSerializer,
    BroadcastSerializer,
    PlatformBroadcastMediaSerializer,
    PlatformBroadcastSerializer,
)
from apps.broadcasts.tasks import send_broadcast, send_platform_broadcast


def _media_file_response(media) -> HttpResponse:
    """Hands the actual bytes off to nginx via X-Accel-Redirect instead of
    streaming them through this app process (see nginx/app.conf's
    `/internal-media/` location, `internal` so it's unreachable except via
    this header). The response Django sends here still carries the real
    Content-Type/Content-Disposition — nginx only ever substitutes the
    body — so the tenant-scoped auth check in `.get_object()` above the
    call site remains the only way to reach a given file; nginx just
    serves the bytes once that check has already passed.

    Content-Disposition is always `attachment` (audit finding H-1, second
    layer alongside the upload-time validation in serializers.py): the
    admin panel never navigates the browser to this URL directly — every
    caller (MediaAttach preview, broadcast history thumbnails) goes through
    apiFetchObjectUrl, which `fetch()`s the bytes and renders them from a
    Blob, where Content-Disposition has no effect either way. `attachment`
    costs that flow nothing, and it closes off the one path that isn't
    covered by upload-time validation alone: a user manually opening this
    URL directly (e.g. "open image in new tab") would otherwise have the
    browser render whatever Content-Type is stored, inline, in this app's
    own origin."""
    response = HttpResponse(content_type=media.content_type or "application/octet-stream")
    response["X-Accel-Redirect"] = f"/internal-media/{quote(media.file.name)}"
    disposition = content_disposition_header(True, media.original_filename or "media")
    if disposition:
        response["Content-Disposition"] = disposition
    return response


def _quota_exceeded(tenant) -> bool:
    """CLAUDE.md-adjacent monetization lever: superadmin sets a per-tenant
    monthly cap (Tenant.broadcast_quota, null = unlimited), shared across all
    of that tenant's tenant_admin logins. Resets automatically every
    calendar month by simply counting this-month sends rather than storing
    and resetting a counter. platform_broadcast__isnull=True excludes
    superadmin-originated legs (apps.broadcasts.tasks.send_platform_broadcast)
    from ever counting against a tenant's own quota."""
    if tenant.broadcast_quota is None:
        return False
    now = timezone.localtime(timezone.now())
    used = Broadcast.objects.filter(
        tenant=tenant,
        platform_broadcast__isnull=True,
        status__in=[Broadcast.Status.SENDING, Broadcast.Status.SENT, Broadcast.Status.FAILED],
        created_at__year=now.year,
        created_at__month=now.month,
    ).count()
    return used >= tenant.broadcast_quota


class BroadcastViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §7c: tenant admin composes and sends broadcasts within
    their own tenant."""

    serializer_class = BroadcastSerializer
    permission_classes = [IsTenantAdmin]

    def get_queryset(self):
        return Broadcast.objects.all().order_by("-created_at")

    def perform_create(self, serializer):
        broadcast = serializer.save(
            tenant=self.request.user.profile.tenant, created_by=self.request.user
        )
        log_action(
            tenant=broadcast.tenant,
            actor=self.request.user,
            action="broadcast_created",
            target_type="Broadcast",
            target_id=broadcast.id,
            metadata={"title": broadcast.title, "has_media": broadcast.media_id is not None},
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Locks and flips the broadcast to SENDING synchronously, before
        enqueuing the Celery task — not after it starts running. Without
        this, the row stays in DRAFT status (and thus re-sendable) for the
        whole gap between this request returning and the worker picking up
        the task, so two overlapping `send` calls on the same broadcast
        (or the row's Yuborish button still being clickable in that window)
        could both pass the status check and double-enqueue the send.
        """
        broadcast = self.get_object()
        if _quota_exceeded(broadcast.tenant):
            return Response(
                {"detail": "Bu oy uchun xabarnoma yuborish limiti tugadi."}, status=400
            )
        with transaction.atomic():
            locked = Broadcast.objects.select_for_update().get(pk=broadcast.pk)
            if locked.status != Broadcast.Status.DRAFT:
                return Response({"detail": "Only a draft broadcast can be sent."}, status=400)
            locked.status = Broadcast.Status.SENDING
            locked.save(update_fields=["status"])

        send_broadcast.delay(locked.pk)
        log_action(
            tenant=locked.tenant,
            actor=request.user,
            action="broadcast_sent",
            target_type="Broadcast",
            target_id=locked.id,
            metadata={"title": locked.title},
        )
        return Response(BroadcastSerializer(locked).data)


class BroadcastMediaViewSet(viewsets.ModelViewSet):
    """Upload endpoint for a broadcast's image/video (CLAUDE.md §7c rich
    composer). No update/destroy — a composer that wants different media
    just uploads a new row and points media_id at it. `file` streams the
    bytes back for the live preview / history thumbnail, scoped through the
    same tenant-filtered queryset as everything else here (CLAUDE.md §4) —
    the isolation boundary is this queryset, not the storage path."""

    serializer_class = BroadcastMediaSerializer
    permission_classes = [IsTenantAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return BroadcastMedia.objects.all().order_by("-created_at")

    def perform_create(self, serializer):
        uploaded_file = serializer.validated_data["file"]
        content_type = uploaded_file.content_type or ""
        media_type = (
            BroadcastMedia.MediaType.IMAGE
            if content_type.startswith("image/")
            else BroadcastMedia.MediaType.VIDEO
        )
        serializer.save(
            tenant=self.request.user.profile.tenant,
            uploaded_by=self.request.user,
            media_type=media_type,
            original_filename=uploaded_file.name,
            content_type=content_type,
            size_bytes=uploaded_file.size,
        )

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        media = self.get_object()
        return _media_file_response(media)


class PlatformBroadcastViewSet(viewsets.ModelViewSet):
    """Superadmin-only: compose a broadcast fanned out to every active
    tenant's customers (CLAUDE.md §7c superadmin dashboard). Deliberately
    permission_classes = [IsSuperadmin] and NOT `IsSuperadmin | IsTenantAdmin`
    — unlike every other tenant-touching viewset here, PlatformBroadcast/
    PlatformBroadcastMedia are plain (non-tenant-scoped) models with no
    TenantManager safety net, so this permission class is the only thing
    standing between "superadmin broadcast composer" and any authenticated
    user reading cross-tenant aggregate stats."""

    serializer_class = PlatformBroadcastSerializer
    permission_classes = [IsSuperadmin]

    def get_queryset(self):
        # Annotated at the query level (SQL JOIN), never via the
        # `.tenant_legs` related manager on an instance — that manager
        # inherits Broadcast's tenant-scoped TenantManager and either raises
        # TenantContextError or (if `.all_tenants()` is used to dodge that)
        # silently returns every Broadcast row in the table, not just this
        # PlatformBroadcast's own legs. annotate()/Count()/Sum() compile to
        # a JOIN and never touch that manager, so this is the safe path —
        # and it makes list/detail a single query each, no N+1.
        return PlatformBroadcast.objects.annotate(
            sent_count=Coalesce(Sum("tenant_legs__sent_count"), 0),
            failed_count=Coalesce(Sum("tenant_legs__failed_count"), 0),
            tenant_count=Count("tenant_legs", distinct=True),
        ).order_by("-created_at")

    def perform_create(self, serializer):
        platform_broadcast = serializer.save(created_by=self.request.user)
        log_action(
            tenant=None,
            actor=self.request.user,
            action="platform_broadcast_created",
            target_type="PlatformBroadcast",
            target_id=platform_broadcast.id,
            metadata={
                "title": platform_broadcast.title,
                "has_media": platform_broadcast.media_id is not None,
            },
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Same lock/flip-then-enqueue double-submit guard as
        BroadcastViewSet.send() — see that method's docstring."""
        platform_broadcast = self.get_object()
        with transaction.atomic():
            locked = PlatformBroadcast.objects.select_for_update().get(pk=platform_broadcast.pk)
            if locked.status != PlatformBroadcast.Status.DRAFT:
                return Response(
                    {"detail": "Only a draft broadcast can be sent."}, status=400
                )
            locked.status = PlatformBroadcast.Status.SENDING
            locked.save(update_fields=["status"])

        send_platform_broadcast.delay(locked.pk)
        log_action(
            tenant=None,
            actor=request.user,
            action="platform_broadcast_sent",
            target_type="PlatformBroadcast",
            target_id=locked.id,
            metadata={"title": locked.title},
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=locked.pk)).data)


class PlatformBroadcastMediaViewSet(viewsets.ModelViewSet):
    """Superadmin-only upload endpoint for a platform broadcast's
    image/video — mirrors BroadcastMediaViewSet exactly, against the
    unscoped PlatformBroadcastMedia model (no tenant to scope by yet)."""

    serializer_class = PlatformBroadcastMediaSerializer
    permission_classes = [IsSuperadmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return PlatformBroadcastMedia.objects.all().order_by("-created_at")

    def perform_create(self, serializer):
        uploaded_file = serializer.validated_data["file"]
        content_type = uploaded_file.content_type or ""
        media_type = (
            PlatformBroadcastMedia.MediaType.IMAGE
            if content_type.startswith("image/")
            else PlatformBroadcastMedia.MediaType.VIDEO
        )
        serializer.save(
            uploaded_by=self.request.user,
            media_type=media_type,
            original_filename=uploaded_file.name,
            content_type=content_type,
            size_bytes=uploaded_file.size,
        )

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        media = self.get_object()
        return _media_file_response(media)
