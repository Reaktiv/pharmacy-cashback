from django.db import transaction
from django.http import FileResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsTenantAdmin
from apps.audit.services import log_action
from apps.broadcasts.models import Broadcast, BroadcastMedia
from apps.broadcasts.serializers import BroadcastMediaSerializer, BroadcastSerializer
from apps.broadcasts.tasks import send_broadcast


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
        return FileResponse(
            media.file.open("rb"),
            content_type=media.content_type or "application/octet-stream",
            filename=media.original_filename or "media",
        )
