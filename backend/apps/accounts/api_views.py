from rest_framework import viewsets

from apps.accounts.models import Branch, Seller, UserProfile
from apps.accounts.permissions import IsBranchManager, IsTenantAdmin
from apps.accounts.serializers import BranchSerializer, SellerSerializer


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


class SellerViewSet(viewsets.ModelViewSet):
    """CLAUDE.md §3: tenant admin manages all sellers in their tenant;
    branch manager manages only their own branch's sellers."""

    serializer_class = SellerSerializer
    permission_classes = [IsTenantAdmin | IsBranchManager]

    def get_queryset(self):
        profile = self.request.user.profile
        qs = Seller.objects.all().select_related("branch", "user")
        if profile.role == UserProfile.Role.BRANCH_MANAGER:
            qs = qs.filter(branch_id=profile.branch_id)
        return qs.order_by("full_name")
