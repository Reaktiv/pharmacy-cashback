"""Resolves the current tenant into a ContextVar for the request's duration
(CLAUDE.md §4).

Web (session auth: seller_web, Django admin): resolved from the
authenticated user's UserProfile (apps.accounts, Phase 2) — superadmins have
no single tenant, so their profile.tenant is None and tenant-scoped queries
correctly fail closed for them unless they explicitly use `.all_tenants()`.

API (JWT auth, Phase 7): this middleware runs as plain Django middleware,
which executes *before* DRF's own authentication cycle — DRF resolves
request.user from the JWT lazily, inside the view's dispatch(), which is too
late for this middleware to see. So for requests with no session user, this
also tries JWTAuthentication directly (reusing SimpleJWT's own class, not
reimplementing token verification) to resolve the same user DRF would.

Telegram webhooks: resolved from the bot's webhook_secret, wired in Phase 5.

No direct import of apps.accounts here: `user.profile` is Django's
auto-generated reverse one-to-one accessor (UserProfile.user's related_name),
so this module has no compile-time dependency on the accounts app.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.tenants.context import reset_current_tenant, set_current_tenant


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt_auth = JWTAuthentication()

    def __call__(self, request):
        token = set_current_tenant(self._resolve_tenant(request))
        try:
            response = self.get_response(request)
        finally:
            reset_current_tenant(token)
        return response

    def _resolve_tenant(self, request):
        user = self._resolve_user(request)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        profile = getattr(user, "profile", None)
        return getattr(profile, "tenant", None)

    def _resolve_user(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        try:
            result = self._jwt_auth.authenticate(request)
        except Exception:
            return None
        if result is None:
            return None
        jwt_user, _ = result
        return jwt_user
