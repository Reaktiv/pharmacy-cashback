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
Both this call and DRF's later one go through CachingJWTAuthentication
(apps.tenants.authentication), which memoizes the result on the request so
the token is only decoded and the user only fetched once per request — see
that module's docstring for why a naive two-call setup doubles DB work.

Telegram webhooks: resolved from the bot's webhook_secret, wired in Phase 5.

No direct import of apps.accounts here: `user.profile` is Django's
auto-generated reverse one-to-one accessor (UserProfile.user's related_name),
so this module has no compile-time dependency on the accounts app.
"""

from apps.tenants.authentication import CachingJWTAuthentication
from apps.tenants.context import reset_current_tenant, set_current_tenant


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt_auth = CachingJWTAuthentication()

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
        # JWT first, session as fallback — not the reverse. A browser can
        # legitimately carry both an unrelated Django session cookie (e.g.
        # a seller_web login from earlier, on a different tenant) and a
        # JWT bearer token (the React panel) at the same time, since both
        # ride the same origin. DRF's own view-level auth only ever
        # consults the JWT (REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES
        # has no SessionAuthentication) — checking the session first here
        # would bind this request's tenant context to the *session's*
        # tenant while permission checks and request.user in the view use
        # the JWT's tenant, a split-brain that silently scopes
        # TenantManager-filtered queries (CLAUDE.md §4) to the wrong
        # tenant instead of 403/404ing. Only fall back to the session when
        # there's no JWT to decode (plain session-based apps: seller_web,
        # Django admin, accounts web login never send an Authorization
        # header, so this is a no-op behavior change for them).
        try:
            result = self._jwt_auth.authenticate(request)
        except Exception:
            result = None
        if result is not None:
            jwt_user, _ = result
            return jwt_user
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        return None
