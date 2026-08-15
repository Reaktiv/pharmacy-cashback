import asyncio

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import AsyncClient, RequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

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


@pytest.mark.django_db(transaction=True)
def test_concurrent_requests_from_different_tenants_never_cross_contaminate(
    make_user, make_tenant, make_branch
):
    """Regression test for the real ASGI entry point (uvicorn ->
    ASGIHandler), not just the middleware in isolation. The tests above all
    call TenantMiddleware(get_response)(request) directly and synchronously
    — they never pass through Django's actual adaptation of a mixed sync/
    async MIDDLEWARE chain (TenantMiddleware is a plain sync middleware
    sandwiched between async-capable ones — see MIDDLEWARE in
    config/settings.py), which is what production traffic under uvicorn
    actually does. django.test.AsyncClient drives requests through that
    real ASGIHandler path, so firing many concurrent, interleaved requests
    from two different tenants here is the faithful way to catch a
    contextvar that got lost or mixed up across that boundary — it would
    show up as either a 500 (TenantContextError) or, worse, one tenant's
    admin seeing the other's data. transaction=True: concurrent requests
    can be served on different threads (thread_sensitive sync_to_async),
    which each need their own real DB connection — the default django_db
    fixture's single wrapping transaction isn't safe to share across
    threads like that."""
    tenant_a = make_tenant("concurrent-a")
    tenant_b = make_tenant("concurrent-b")
    make_branch(tenant_a, name="ONLY_IN_TENANT_A")
    make_branch(tenant_b, name="ONLY_IN_TENANT_B")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    admin_b = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)
    token_a = str(RefreshToken.for_user(admin_a).access_token)
    token_b = str(RefreshToken.for_user(admin_b).access_token)

    async def _run():
        client = AsyncClient()

        async def hit(token, label):
            response = await client.get(
                "/api/branches/", headers={"Authorization": f"Bearer {token}"}
            )
            return label, response.status_code, response.content.decode()

        tasks = [
            hit(token_a if i % 2 == 0 else token_b, "A" if i % 2 == 0 else "B") for i in range(20)
        ]
        return await asyncio.gather(*tasks)

    results = asyncio.run(_run())

    # Each concurrent request may have been served on its own thread
    # (thread_sensitive sync_to_async), each opening its own DB connection
    # — close them explicitly, or pytest-django's end-of-session "drop the
    # test database" can warn/fail with "database is being accessed by
    # other users" once a lingering one is still open.
    from django.db import connections

    connections.close_all()

    assert len(results) == 20
    for label, status, body in results:
        assert status == 200, f"{label} got {status}: {body}"
        own, other = (
            ("ONLY_IN_TENANT_A", "ONLY_IN_TENANT_B")
            if label == "A"
            else (
                "ONLY_IN_TENANT_B",
                "ONLY_IN_TENANT_A",
            )
        )
        assert own in body, f"{label} didn't see its own branch: {body}"
        assert other not in body, f"{label} saw the other tenant's branch: {body}"
