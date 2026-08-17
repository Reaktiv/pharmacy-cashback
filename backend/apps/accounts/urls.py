from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import MeView, TenantAwareTokenObtainPairView, TokenLogoutView

urlpatterns = [
    path("token/", TenantAwareTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/logout/", TokenLogoutView.as_view(), name="token_logout"),
    path("me/", MeView.as_view(), name="me"),
]
