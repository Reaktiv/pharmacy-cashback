from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsTenantAdmin
from apps.audit.services import log_action
from apps.broadcasts.models import Broadcast
from apps.broadcasts.serializers import BroadcastSerializer
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
            metadata={"title": broadcast.title},
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        broadcast = self.get_object()
        if broadcast.status != Broadcast.Status.DRAFT:
            return Response({"detail": "Only a draft broadcast can be sent."}, status=400)
        send_broadcast.delay(broadcast.pk)
        log_action(
            tenant=broadcast.tenant,
            actor=request.user,
            action="broadcast_sent",
            target_type="Broadcast",
            target_id=broadcast.id,
            metadata={"title": broadcast.title},
        )
        return Response(BroadcastSerializer(broadcast).data)
