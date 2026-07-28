import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.accounts.models import UserProfile
from apps.tenants.context import get_current_tenant
from apps.tenants.middleware import TenantMiddleware

factory = RequestFactory()


def _run_middleware(user):
    """Runs TenantMiddleware directly against a bare request, recording what
    get_current_tenant() sees *while the inner view is executing* — this is
    what TenantManager.get_queryset() actually reads. Simulating
    request.user directly (rather than going through DRF's force_authenticate,
    which only patches the DRF-wrapped request after Django's own middleware
    has already run) is what makes this a faithful test of the middleware
    itself.
    """
    seen = {}

    def get_response(request):
        seen["tenant"] = get_current_tenant()
        return "response"

    request = factory.get("/")
    request.user = user
    TenantMiddleware(get_response)(request)
    return seen["tenant"]


@pytest.mark.django_db
def test_middleware_binds_tenant_from_authenticated_users_profile(make_user, make_tenant):
    tenant = make_tenant("t")
    tenant_admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)

    assert _run_middleware(tenant_admin) == tenant


@pytest.mark.django_db
def test_middleware_leaves_context_unset_for_superadmin(make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)

    assert _run_middleware(superadmin) is None


def test_middleware_leaves_context_unset_for_anonymous_user():
    assert _run_middleware(AnonymousUser()) is None


@pytest.mark.django_db
def test_middleware_resets_context_after_the_request(make_user, make_tenant):
    tenant = make_tenant("t")
    tenant_admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)

    assert get_current_tenant() is None  # nothing bound before the request

    _run_middleware(tenant_admin)

    assert get_current_tenant() is None  # and nothing leaks after it either


@pytest.mark.django_db
def test_middleware_does_not_leak_tenant_across_requests(make_user, make_tenant):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    admin_b = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)

    assert _run_middleware(admin_a) == tenant_a
    assert _run_middleware(admin_b) == tenant_b
    assert get_current_tenant() is None
