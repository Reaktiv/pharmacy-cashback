"""A caching wrapper around SimpleJWT's JWTAuthentication.

TenantMiddleware (apps.tenants.middleware) must resolve request.user *before*
DRF's own authentication cycle runs, so it calls JWTAuthentication.authenticate()
itself. DRF then calls it again inside the view's dispatch(). Left plain, that
decodes the token and hits the DB for the User twice per request, and because
the two calls produce two separate User instances, `.profile` (a reverse
OneToOneField, cached per-instance by Django) gets queried again on whichever
instance is touched first in the middleware and again in the view.

CachingJWTAuthentication fixes both: it memoizes its result on the raw
HttpRequest so the second .authenticate() call is free, and it
select_related()s `profile` so the one real User query fetches both in a
single round trip.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

_CACHE_ATTR = "_tenant_jwt_auth_cache"
_UNSET = object()


class CachingJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # DRF wraps the raw HttpRequest in its own Request object for the
        # view's auth cycle; TenantMiddleware calls us with the raw request
        # directly. `._request` unwraps back to the same underlying object
        # either way, so the cache is shared between both call sites.
        raw_request = getattr(request, "_request", request)

        cached = getattr(raw_request, _CACHE_ATTR, _UNSET)
        if cached is not _UNSET:
            if isinstance(cached, Exception):
                raise cached
            return cached

        try:
            result = super().authenticate(request)
        except Exception as exc:
            setattr(raw_request, _CACHE_ATTR, exc)
            raise
        setattr(raw_request, _CACHE_ATTR, result)
        return result

    def get_user(self, validated_token):
        """Mirrors JWTAuthentication.get_user, but select_related()s
        `profile` (and `profile__tenant`, which TenantMiddleware reads on
        every authenticated request to bind the ContextVar) so they're
        fetched alongside the user instead of as separate queries the first
        time `request.user.profile`/`.profile.tenant` are touched."""
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken(
                _("Token contained no recognizable user identification")
            ) from None

        try:
            user = self.user_model.objects.select_related("profile__tenant").get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except self.user_model.DoesNotExist:
            raise AuthenticationFailed(_("User not found"), code="user_not_found") from None

        if not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

        if api_settings.CHECK_REVOKE_TOKEN:
            if validated_token.get(
                api_settings.REVOKE_TOKEN_CLAIM
            ) != get_md5_hash_password(user.password):
                raise AuthenticationFailed(
                    _("The user's password has been changed."), code="password_changed"
                )

        return user
