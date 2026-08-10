from rest_framework.routers import DefaultRouter

from apps.accounts.api_views import (
    BranchManagerViewSet,
    BranchViewSet,
    SellerViewSet,
    TenantAdminViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("branch-managers", BranchManagerViewSet, basename="branch-manager")
router.register("tenant-admins", TenantAdminViewSet, basename="tenant-admin")
router.register("sellers", SellerViewSet, basename="seller")

urlpatterns = router.urls
