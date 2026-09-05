"""A superadmin-deactivated Tenant locks out every login tied to it —
its tenant admins, branch managers and sellers — both at the login
endpoints and on tokens that were already issued while it was active.
Superadmins have no tenant and stay unaffected.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile


@pytest.mark.django_db
def test_existing_jwt_session_is_refused_once_the_tenant_is_deactivated(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("dorimed")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant, username="admin1")
    client = api_client_for(admin)

    assert client.get("/api/me/").status_code == 200

    tenant.is_active = False
    tenant.save(update_fields=["is_active"])

    response = client.get("/api/me/")
    assert response.status_code == 401
    assert "Kirish huquqingiz yo'q" in str(response.data["detail"])


@pytest.mark.django_db
def test_branch_manager_is_locked_out_too(api_client_for, make_user, make_tenant, make_branch):
    tenant = make_tenant("dorimed")
    branch = make_branch(tenant)
    manager = make_user(
        role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch, username="bm1"
    )
    client = api_client_for(manager)
    assert client.get("/api/me/").status_code == 200

    tenant.is_active = False
    tenant.save(update_fields=["is_active"])

    assert client.get("/api/me/").status_code == 401


@pytest.mark.django_db
def test_login_is_refused_while_the_tenant_is_deactivated(make_user, make_tenant):
    tenant = make_tenant("dorimed")
    make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant, username="admin1")
    tenant.is_active = False
    tenant.save(update_fields=["is_active"])

    response = APIClient().post(
        "/api/auth/token/", {"username": "admin1", "password": "pass1234"}, format="json"
    )
    assert response.status_code == 401
    assert "Kirish huquqingiz yo'q" in str(response.data["detail"])


@pytest.mark.django_db
def test_access_is_restored_when_the_tenant_is_reactivated(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("dorimed")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant, username="admin1")
    client = api_client_for(admin)

    tenant.is_active = False
    tenant.save(update_fields=["is_active"])
    assert client.get("/api/me/").status_code == 401

    tenant.is_active = True
    tenant.save(update_fields=["is_active"])
    assert client.get("/api/me/").status_code == 200


@pytest.mark.django_db
def test_superadmin_is_unaffected_by_any_tenant_deactivation(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("dorimed")
    tenant.is_active = False
    tenant.save(update_fields=["is_active"])

    superadmin = make_user(role=UserProfile.Role.SUPERADMIN, username="root")
    client = api_client_for(superadmin)

    assert client.get("/api/me/").status_code == 200
