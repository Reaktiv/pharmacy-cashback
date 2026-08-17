from django.contrib.auth.views import LoginView, LogoutView
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.ratelimit import (
    RateLimitExceededError,
    check_rate_limit,
    client_identity,
    release_rate_limit_slot,
    reserve_rate_limit_slot,
)
from apps.accounts.serializers import TenantAwareTokenObtainPairSerializer
from apps.seller_web.i18n import LANGUAGES, get_language, strings_for
from apps.tenants.models import GlobalSettings

SELLER_LOGIN_ATTEMPT_LIMIT = 5
SELLER_LOGIN_ATTEMPT_WINDOW_SECONDS = 300

ADMIN_LOGIN_ATTEMPT_LIMIT = 5
ADMIN_LOGIN_ATTEMPT_WINDOW_SECONDS = 60


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


class TenantAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = TenantAwareTokenObtainPairSerializer  # type: ignore[assignment]

    def post(self, request, *args, **kwargs):
        # DRF's AnonRateThrottle (the old approach here) counts every
        # request, right or wrong password — an admin logging in correctly
        # several times in a row (multiple tabs/devices) got locked out for
        # minutes despite never once getting it wrong. Reserve/release
        # pattern instead (apps.accounts.ratelimit, same as SellerLoginView's
        # OTP-redeem-flow counterpart in apps.ledger.services): reserving up
        # front is an atomic increment (race-safe under concurrent
        # requests — audit finding M-1), and a *correct* password releases
        # the reservation again, so only wrong passwords actually count.
        attempt_key = f"admin_login_attempts:{client_identity(request)}"
        try:
            reserve_rate_limit_slot(
                key=attempt_key,
                limit=ADMIN_LOGIN_ATTEMPT_LIMIT,
                window_seconds=ADMIN_LOGIN_ATTEMPT_WINDOW_SECONDS,
            )
        except RateLimitExceededError as exc:
            # reserve_rate_limit_slot raises a plain-Django exception (see
            # SellerLoginView's own try/except above) — DRF only
            # auto-converts its own exception types into a response, so
            # this must become a Throttled (429) explicitly or it
            # surfaces as an unhandled 500.
            raise Throttled(detail=str(exc)) from exc

        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            raise
        else:
            release_rate_limit_slot(key=attempt_key)
            return response


class TokenLogoutView(APIView):
    """Audit finding H-3: without this, there was no way to end a JWT
    session server-side at all — only a client-side sessionStorage.clear()
    that left the (still perfectly valid) refresh token usable by anyone
    who'd captured it (e.g. via the stored-XSS path fixed in H-1) until it
    naturally expired, up to 24h later. Blacklisting the refresh token here
    means a real logout actually revokes the session, not just forgets it
    locally."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "refresh is required."}, status=400)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            # Already expired/blacklisted/malformed — logout still succeeds
            # either way, since the end state (this token unusable) is the
            # same regardless of which of those it was.
            pass
        return Response(status=204)


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
