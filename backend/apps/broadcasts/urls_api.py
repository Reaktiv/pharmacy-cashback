from rest_framework.routers import DefaultRouter

from apps.broadcasts.api_views import BroadcastViewSet

router = DefaultRouter()
router.register("broadcasts", BroadcastViewSet, basename="broadcast")

urlpatterns = router.urls
