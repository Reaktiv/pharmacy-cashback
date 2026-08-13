from django.contrib.auth.views import LoginView, LogoutView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.ratelimit import RateLimitExceededError, check_rate_limit, client_identity
from apps.accounts.serializers import TenantAwareTokenObtainPairSerializer
from apps.seller_web.i18n import LANGUAGES, get_language, strings_for
from apps.tenants.models import GlobalSettings

SELLER_LOGIN_ATTEMPT_LIMIT = 5
SELLER_LOGIN_ATTEMPT_WINDOW_SECONDS = 300


class SellerLoginView(LoginView):
    """Session-based browser login (CLAUDE.md §7b) — distinct from the JWT
    API used by the React admin panel (§7c). Only used by the seller-web
    register page for now; redirect target is fixed accordingly."""

    template_name = "accounts/login.html"

    def post(self, request, *args, **kwargs):
        # Plain Django view — DRF's throttle classes (see
        # TenantAwareTokenObtainPairView below) never reach this, so it
        # needs its own limit against password-guessing.
        try:
            check_rate_limit(
                key=f"seller_login_attempts:{client_identity(request)}",
                limit=SELLER_LOGIN_ATTEMPT_LIMIT,
                window_seconds=SELLER_LOGIN_ATTEMPT_WINDOW_SECONDS,
            )
        except RateLimitExceededError as exc:
            form = self.get_form()
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

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


class LoginRateThrottle(AnonRateThrottle):
    """5 attempts per 5 minutes per client — matches the window used by the
    custom limiter on the two plain-Django login/redeem views (see
    apps.accounts.ratelimit). DRF's "N/period" rate strings only support
    whole s/m/h/d windows, so num_requests/duration are set directly here
    instead."""

    scope = "login"

    def __init__(self):
        self.num_requests = 5
        self.duration = 300
        # allow_request() only checks this for `is None` (meaning "no
        # throttling") — it never re-parses the string once num_requests/
        # duration are already set above, so this is just documentation.
        self.rate = f"{self.num_requests}/{self.duration}s"


class TenantAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = TenantAwareTokenObtainPairSerializer  # type: ignore[assignment]
    throttle_classes = [LoginRateThrottle]


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
