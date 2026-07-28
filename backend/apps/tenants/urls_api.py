from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.tenants.api_views import BotViewSet, GlobalSettingsView, TenantViewSet

router = DefaultRouter()
router.register("tenants", TenantViewSet, basename="tenant")
router.register("bots", BotViewSet, basename="bot")

urlpatterns = [
    path("global-settings/", GlobalSettingsView.as_view(), name="global-settings"),
    *router.urls,
]
