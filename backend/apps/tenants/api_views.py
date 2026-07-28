from rest_framework import generics, viewsets
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import UserProfile
from apps.accounts.permissions import IsSuperadmin, IsTenantAdmin
from apps.audit.services import log_action
from apps.tenants.models import Bot, GlobalSettings, Tenant
from apps.tenants.serializers import BotSerializer, GlobalSettingsSerializer, TenantSerializer


class TenantViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §7c: superadmin manages all tenants; a tenant admin can
    view/update only their own (queryset scoping below handles this — a
    tenant admin requesting any other tenant's id simply 404s)."""

    serializer_class = TenantSerializer
    permission_classes = [IsSuperadmin | IsTenantAdmin]

    def get_queryset(self):
        profile = self.request.user.profile
        if profile.role == UserProfile.Role.SUPERADMIN:
            return Tenant.objects.all().order_by("name")
        return Tenant.objects.filter(pk=profile.tenant_id)

    def perform_create(self, serializer):
        if self.request.user.profile.role != UserProfile.Role.SUPERADMIN:
            raise PermissionDenied("Only a superadmin can create tenants.")
        tenant = serializer.save()
        log_action(
            tenant=tenant,
            actor=self.request.user,
            action="tenant_created",
            target_type="Tenant",
            target_id=tenant.id,
            metadata={"name": tenant.name, "slug": tenant.slug},
        )

    def perform_update(self, serializer):
        old_rate = serializer.instance.cashback_rate
        tenant = serializer.save()
        if tenant.cashback_rate != old_rate:
            log_action(
                tenant=tenant,
                actor=self.request.user,
                action="rate_change",
                target_type="Tenant",
                target_id=tenant.id,
                metadata={"old_rate": str(old_rate), "new_rate": str(tenant.cashback_rate)},
            )

    def perform_destroy(self, instance):
        if self.request.user.profile.role != UserProfile.Role.SUPERADMIN:
            raise PermissionDenied("Only a superadmin can delete tenants.")
        instance.delete()


class GlobalSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = GlobalSettingsSerializer
    permission_classes = [IsSuperadmin]

    def get_object(self):
        return GlobalSettings.load()


class BotViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §7c: bot/token management — superadmin only."""

    serializer_class = BotSerializer
    permission_classes = [IsSuperadmin]

    def get_queryset(self):
        return Bot.objects.all_tenants().order_by("username")

    def perform_create(self, serializer):
        bot = serializer.save()
        log_action(
            tenant=bot.tenant,
            actor=self.request.user,
            action="bot_created",
            target_type="Bot",
            target_id=bot.id,
            metadata={"username": bot.username},  # never the token itself
        )

    def perform_update(self, serializer):
        token_rotated = bool(serializer.validated_data.get("token"))
        bot = serializer.save()
        if token_rotated:
            log_action(
                tenant=bot.tenant,
                actor=self.request.user,
                action="bot_token_rotated",
                target_type="Bot",
                target_id=bot.id,
                metadata={"username": bot.username},
            )
