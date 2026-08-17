from decimal import Decimal

import pytest
from apps.accounts.models import Branch, Seller, UserProfile
from apps.customers.models import Customer
from apps.tenants.models import Tenant
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _isolate_media_root(settings, tmp_path):
    """File-upload tests must never write into the real dev backend/media/
    directory (the default MEDIA_ROOT) — it's shared, persistent across
    runs, and can accumulate root-owned subdirectories from local Docker
    use (the `web` container writes into it as root via a bind mount),
    which then breaks every upload test with a PermissionError that has
    nothing to do with the test itself. Every test gets its own disposable
    directory instead, so the suite is hermetic regardless of what's on
    disk in the real dev media folder."""
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture(autouse=True)
def _clear_cache():
    """The Django cache (GlobalSettings.load(), see apps.tenants.models) is
    a real shared Redis instance, not per-test DB state — Django's usual
    per-test transaction rollback doesn't touch it. Without this, a value
    cached by one test (e.g. GlobalSettings, always pk=1) would leak into
    the next test's assertions."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_tenant(db):
    def _make(slug="tenant", rate=Decimal("5.00")):
        return Tenant.objects.create(name=slug.title(), slug=slug, cashback_rate=rate)

    return _make


@pytest.fixture
def make_branch(db):
    def _make(tenant, name="Main Branch"):
        # Branch is a TenantScopedModel; all_tenants() sidesteps needing a
        # bound tenant context just to set up test fixtures.
        return Branch.objects.all_tenants().create(tenant=tenant, name=name)

    return _make


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(role=None, tenant=None, branch=None, username=None):
        counter["n"] += 1
        username = username or f"user{counter['n']}"
        user = User.objects.create_user(username=username, password="pass1234")
        if role is not None:
            # create_user() above already triggered the post_save signal that
            # gives `user` a cached UNASSIGNED profile object; update_or_create
            # here updates the *row* but not that cached object, so reassign it
            # or `user.profile` would keep returning the stale unassigned one.
            profile, _ = UserProfile.objects.update_or_create(
                user=user, defaults={"role": role, "tenant": tenant, "branch": branch}
            )
            user.profile = profile
        return user

    return _make


@pytest.fixture
def make_customer(db):
    counter = {"n": 0}

    def _make(tenant, phone=None, full_name="Test Customer"):
        counter["n"] += 1
        phone = phone or f"+99890000{counter['n']:04d}"
        return Customer.objects.all_tenants().create(
            tenant=tenant, phone=phone, full_name=full_name
        )

    return _make


@pytest.fixture
def make_seller(db, make_user):
    counter = {"n": 0}

    def _make(tenant, branch):
        counter["n"] += 1
        user = make_user(
            role=UserProfile.Role.SELLER,
            tenant=tenant,
            branch=branch,
            username=f"seller{counter['n']}",
        )
        return Seller.objects.all_tenants().create(
            tenant=tenant,
            branch=branch,
            user=user,
            phone=f"+99891000{counter['n']:04d}",
            full_name=f"Seller {counter['n']}",
        )

    return _make


@pytest.fixture
def api_client_for(db):
    """Returns an APIClient carrying a real JWT for the given user (all
    users from make_user/make_seller have password 'pass1234') — obtained
    via the real /api/auth/token/ endpoint, not force_authenticate, so the
    full auth cycle (including TenantMiddleware's JWT fallback) is actually
    exercised, the same way a real client hits the API.
    """

    def _make(user, password="pass1234"):
        client = APIClient()
        response = client.post(
            "/api/auth/token/",
            {"username": user.username, "password": password},
            format="json",
        )
        assert response.status_code == 200, response.data
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client

    return _make
