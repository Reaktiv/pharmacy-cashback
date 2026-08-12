from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts.api_views import (
    BranchManagerViewSet,
    BranchViewSet,
    ChangePasswordView,
    MeAvatarView,
    MeTenantLogoView,
    MeView,
    SellerViewSet,
    TenantAdminViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("branch-managers", BranchManagerViewSet, basename="branch-manager")
router.register("tenant-admins", TenantAdminViewSet, basename="tenant-admin")
router.register("sellers", SellerViewSet, basename="seller")

urlpatterns = router.urls + [
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", MeAvatarView.as_view(), name="me-avatar"),
    path("me/tenant-logo/", MeTenantLogoView.as_view(), name="me-tenant-logo"),
    path("me/change-password/", ChangePasswordView.as_view(), name="me-change-password"),
]
