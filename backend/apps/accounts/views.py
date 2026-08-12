from django.contrib.auth.views import LoginView, LogoutView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.serializers import TenantAwareTokenObtainPairSerializer
from apps.seller_web.i18n import LANGUAGES, get_language, strings_for
from apps.tenants.models import GlobalSettings


class SellerLoginView(LoginView):
    """Session-based browser login (CLAUDE.md §7b) — distinct from the JWT
    API used by the React admin panel (§7c). Only used by the seller-web
    register page for now; redirect target is fixed accordingly."""

    template_name = "accounts/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        language = get_language(self.request)
        context["s"] = strings_for(language)
        context["language"] = language
        context["languages"] = LANGUAGES
        # Pre-login, no tenant is known yet — this always shows the
        # product's own brand (superadmin-editable, see MeSerializer.
        # platform_name), same as the React panel's LoginPage. Read
        # GlobalSettings directly (same process) rather than round-tripping
        # through /api/branding/ — Django server-rendering this page can
        # just do that; the React panel can't, hence its own public fetch.
        gs = GlobalSettings.load()
        context["platform_name"] = gs.platform_name
        context["has_platform_logo"] = bool(gs.platform_logo)
        return context


class SellerLogoutView(LogoutView):
    next_page = "accounts:login"


class TenantAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = TenantAwareTokenObtainPairSerializer  # type: ignore[assignment]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "profile", None)
        return Response(
            {
                "username": request.user.username,
                "role": profile.role if profile else None,
                "tenant_id": profile.tenant_id if profile else None,
                "tenant_slug": profile.tenant.slug if profile and profile.tenant_id else None,
                "branch_id": profile.branch_id if profile else None,
            }
        )
