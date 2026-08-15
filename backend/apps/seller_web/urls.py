from django.urls import path

from apps.seller_web import views

app_name = "seller_web"

urlpatterns = [
    path("", views.register, name="register"),
    path("earn/", views.earn, name="earn"),
    path("redeem/", views.redeem, name="redeem"),
    path("tenant-logo/", views.tenant_logo, name="tenant_logo"),
    path("set-language/", views.set_language, name="set_language"),
]
