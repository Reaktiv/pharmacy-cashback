from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthcheck, name="healthcheck"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.tenants.urls_api")),
    path("api/", include("apps.accounts.urls_api")),
    path("api/", include("apps.ledger.urls_api")),
    path("api/", include("apps.broadcasts.urls_api")),
    path("accounts/", include("apps.accounts.web_urls")),
    path("seller/", include("apps.seller_web.urls")),
    path("webhook/", include("apps.bot.urls")),
]
