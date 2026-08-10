from rest_framework import viewsets

from apps.accounts.models import Branch, Seller, UserProfile
from apps.accounts.permissions import IsBranchManager, IsSuperadmin, IsTenantAdmin
from apps.accounts.serializers import (
    BranchManagerSerializer,
    BranchSerializer,
    SellerSerializer,
    TenantAdminSerializer,
)
from apps.audit.services import log_action


class BranchViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §3: "Tenant Admin: Manage branches." Branch.objects is
    already tenant-scoped via the ambient TenantManager (TenantMiddleware
    binds it from request.user.profile.tenant), so no extra filtering is
    needed here."""

    serializer_class = BranchSerializer
    permission_classes = [IsTenantAdmin]

    def get_queryset(self):
        return Branch.objects.all().order_by("name")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.profile.tenant)

    def perform_destroy(self, instance):
        # The frontend makes the user confirm this twice — once generically,
        # once specifically warning that ledger history goes with it — before
        # this DELETE is ever sent, so by the time we're here the deletion
        # (including the branch's transactions) is fully intentional.
        from apps.customers.models import PendingCashback
        from apps.ledger.models import Transaction

        # PendingCashback.branch/source_transaction are PROTECT, so it has to
        # go before the transactions it may point to.
        PendingCashback.objects.filter(branch=instance).delete()

        txns = Transaction.objects.filter(branch=instance)
        txn_count = txns.count()
        # Transaction.reverses is a self-referential PROTECT FK — clear it
        # first so a reversal row doesn't block deleting the row it reverses
        # in the same bulk delete.
        txns.update(reverses=None)
        txns.delete()

        # A branch manager/seller without a branch is meaningless, so their
        # logins go with it — the same full-login cleanup used when deleting
        # them directly (see BranchManagerViewSet/SellerViewSet.perform_destroy).
        for seller in Seller.objects.filter(branch=instance).select_related("user"):
            seller.user.delete()
        for manager in UserProfile.objects.filter(
            role=UserProfile.Role.BRANCH_MANAGER, branch=instance
        ).select_related("user"):
            manager.user.delete()

        log_action(
            tenant=instance.tenant,
            actor=self.request.user,
            action="branch_deleted",
            target_type="Branch",
            target_id=instance.id,
            metadata={"name": instance.name, "transactions_deleted": txn_count},
        )
        instance.delete()


class BranchManagerViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §3: only the tenant admin creates/manages branch managers —
    sellers are managed by the branch manager themselves (see SellerViewSet),
    not by the tenant admin directly."""

    serializer_class = BranchManagerSerializer
    permission_classes = [IsTenantAdmin]

    def get_queryset(self):
        tenant = self.request.user.profile.tenant
        return (
            UserProfile.objects.filter(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant)
            .select_related("user", "branch")
            .order_by("user__username")
        )

    def perform_destroy(self, instance):
        log_action(
            tenant=instance.tenant,
            actor=self.request.user,
            action="branch_manager_deleted",
            target_type="UserProfile",
            target_id=instance.id,
            metadata={"username": instance.user.username, "branch": instance.branch.name},
        )
        # Deleting just the profile would strand a live login with no role.
        # UserProfile.user is CASCADE, so removing the User cleans up both.
        instance.user.delete()


class TenantAdminViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §3/§7c: the superadmin creates tenants and is also the only
    role able to provision the tenant admin login that then manages one.
    Cross-tenant by nature (unlike BranchManagerViewSet, which a tenant
    admin only ever sees within their own tenant), so it's superadmin-only
    and scopable by `?tenant=<id>` for the tenant detail page."""

    serializer_class = TenantAdminSerializer
    permission_classes = [IsSuperadmin]

    def get_queryset(self):
        qs = UserProfile.objects.filter(role=UserProfile.Role.TENANT_ADMIN).select_related(
            "user", "tenant"
        )
        tenant_id = self.request.query_params.get("tenant")
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        return qs.order_by("tenant__name", "user__username")

    def perform_create(self, serializer):
        profile = serializer.save()
        log_action(
            tenant=profile.tenant,
            actor=self.request.user,
            action="tenant_admin_created",
            target_type="UserProfile",
            target_id=profile.id,
            metadata={"username": profile.user.username, "tenant": profile.tenant.name},
        )

    def perform_destroy(self, instance):
        log_action(
            tenant=instance.tenant,
            actor=self.request.user,
            action="tenant_admin_deleted",
            target_type="UserProfile",
            target_id=instance.id,
            metadata={"username": instance.user.username, "tenant": instance.tenant.name},
        )
        # Deleting just the profile would strand a live login with no role.
        # UserProfile.user is CASCADE, so removing the User cleans up both.
        instance.user.delete()


class SellerViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §3: only the branch manager creates/manages sellers, scoped
    to their own branch. The tenant admin may still view sellers across
    their tenant for oversight/reporting, but does not add them — that's
    now the branch manager's job, provisioned via BranchManagerViewSet."""

    serializer_class = SellerSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(IsTenantAdmin | IsBranchManager)()]
        return [IsBranchManager()]

    def get_queryset(self):
        profile = self.request.user.profile
        qs = Seller.objects.all().select_related("branch", "user")
        if profile.role == UserProfile.Role.BRANCH_MANAGER:
            qs = qs.filter(branch_id=profile.branch_id)
        return qs.order_by("full_name")

    def perform_destroy(self, instance):
        log_action(
            tenant=instance.tenant,
            actor=self.request.user,
            action="seller_deleted",
            target_type="Seller",
            target_id=instance.id,
            metadata={"full_name": instance.full_name, "branch": instance.branch.name},
        )
        # Seller.user is CASCADE, and Transaction.seller is SET_NULL, so this
        # cleanly removes the login/profile without touching ledger history.
        instance.user.delete()
