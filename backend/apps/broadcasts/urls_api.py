from rest_framework.routers import DefaultRouter

from apps.broadcasts.api_views import BroadcastMediaViewSet, BroadcastViewSet

router = DefaultRouter()
router.register("broadcasts", BroadcastViewSet, basename="broadcast")
router.register("broadcast-media", BroadcastMediaViewSet, basename="broadcast-media")

urlpatterns = router.urls
