"""Session-based browser auth (CLAUDE.md §7b), separate from the JWT API in
urls.py (§7c). Mounted at /accounts/ in config/urls.py."""

from django.urls import path

from apps.accounts.views import SellerLoginView, SellerLogoutView

app_name = "accounts"

urlpatterns = [
    path("login/", SellerLoginView.as_view(), name="login"),
    path("logout/", SellerLogoutView.as_view(), name="logout"),
]
