from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.tenants.api_views import (
    BotViewSet,
    GlobalSettingsView,
    PlatformBrandingView,
    PlatformLogoView,
    TenantViewSet,
)

router = DefaultRouter()
router.register("tenants", TenantViewSet, basename="tenant")
router.register("bots", BotViewSet, basename="bot")

urlpatterns = [
    path("global-settings/", GlobalSettingsView.as_view(), name="global-settings"),
    path("branding/", PlatformBrandingView.as_view(), name="branding"),
    path("branding/logo/", PlatformLogoView.as_view(), name="branding-logo"),
    *router.urls,
]
