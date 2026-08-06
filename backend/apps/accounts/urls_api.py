from rest_framework.routers import DefaultRouter

from apps.accounts.api_views import BranchManagerViewSet, BranchViewSet, SellerViewSet

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("branch-managers", BranchManagerViewSet, basename="branch-manager")
router.register("sellers", SellerViewSet, basename="seller")

urlpatterns = router.urls
