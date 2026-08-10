from rest_framework.routers import DefaultRouter

from apps.broadcasts.api_views import (
    BroadcastMediaViewSet,
    BroadcastViewSet,
    PlatformBroadcastMediaViewSet,
    PlatformBroadcastViewSet,
)

router = DefaultRouter()
router.register("broadcasts", BroadcastViewSet, basename="broadcast")
router.register("broadcast-media", BroadcastMediaViewSet, basename="broadcast-media")
router.register("platform-broadcasts", PlatformBroadcastViewSet, basename="platform-broadcast")
router.register(
    "platform-broadcast-media", PlatformBroadcastMediaViewSet, basename="platform-broadcast-media"
)

urlpatterns = router.urls
