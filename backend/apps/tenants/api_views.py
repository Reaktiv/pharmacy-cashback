from django.db import transaction as db_transaction
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
        old_quota = serializer.instance.broadcast_quota
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
        if tenant.broadcast_quota != old_quota:
            log_action(
                tenant=tenant,
                actor=self.request.user,
                action="broadcast_quota_changed",
                target_type="Tenant",
                target_id=tenant.id,
                metadata={"old_quota": old_quota, "new_quota": tenant.broadcast_quota},
            )

    def perform_destroy(self, instance):
        if self.request.user.profile.role != UserProfile.Role.SUPERADMIN:
            raise PermissionDenied("Only a superadmin can delete tenants.")

        # The frontend makes the superadmin confirm this twice — once
        # generically, once specifically warning that all ledger history
        # goes with it — before this DELETE is ever sent. A plain
        # instance.delete() would otherwise hit Transaction.branch/customer
        # and Seller.branch (both PROTECT) partway through Django's own
        # cascade, so every PROTECT-guarded dependent is cleared explicitly
        # first, in dependency order.
        from apps.broadcasts.models import Broadcast, BroadcastMedia
        from apps.customers.models import PendingCashback
        from apps.ledger.models import Transaction

        # A superadmin has no tenant of their own bound to the ambient
        # context (TenantMiddleware), so every TenantScopedModel query here
        # must go through all_tenants() — the explicit cross-tenant escape
        # hatch (CLAUDE.md §4) — rather than the default tenant-scoped manager.

        # PendingCashback.branch/source_transaction are PROTECT, so it goes
        # before the transactions/branches it may point to.
        PendingCashback.objects.all_tenants().filter(tenant=instance).delete()

        txns = Transaction.objects.all_tenants().filter(tenant=instance)
        txn_count = txns.count()
        # Transaction.reverses is a self-referential PROTECT FK — clear it
        # first so a reversal row doesn't block deleting the row it reverses
        # in the same bulk delete.
        txns.update(reverses=None)
        txns.delete()

        # Broadcast.created_by / BroadcastMedia.uploaded_by are PROTECT(User)
        # — clear before deleting any tenant user's login below.
        Broadcast.objects.all_tenants().filter(tenant=instance).delete()
        BroadcastMedia.objects.all_tenants().filter(tenant=instance).delete()

        # Every login scoped to this tenant (tenant admin, branch managers,
        # sellers) goes with it. Deleting the User cascades UserProfile, and
        # for sellers also their Seller row (both are User-CASCADE).
        for profile in UserProfile.objects.filter(tenant=instance).select_related("user"):
            profile.user.delete()

        # Log before the final delete: AuditLog.tenant is SET_NULL, so the
        # entry survives the cascade, but we need the name/slug captured now.
        log_action(
            tenant=instance,
            actor=self.request.user,
            action="tenant_deleted",
            target_type="Tenant",
            target_id=instance.id,
            metadata={"name": instance.name, "slug": instance.slug, "transactions_deleted": txn_count},
        )
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
        # Captured before save() overwrites token_encrypted — needed to
        # deregister the OLD bot's webhook afterward (see
        # apps.bot.tasks.rotate_bot_credentials). Empty only if this bot
        # somehow never had a token, in which case there's nothing to
        # deregister.
        old_token = (
            serializer.instance.get_token()
            if token_rotated and serializer.instance.token_encrypted
            else None
        )
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
            if old_token:
                from apps.bot.tasks import rotate_bot_credentials

                db_transaction.on_commit(lambda: rotate_bot_credentials.delay(bot.id, old_token))
