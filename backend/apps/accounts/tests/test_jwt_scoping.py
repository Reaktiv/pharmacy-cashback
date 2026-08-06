import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import UserProfile


@pytest.mark.django_db
def test_seller_token_carries_its_own_tenant_and_branch_claims(make_user, make_tenant, make_branch):
    tenant = make_tenant("dorimed")
    branch = make_branch(tenant, name="Chilonzor")
    seller = make_user(
        role=UserProfile.Role.SELLER, tenant=tenant, branch=branch, username="seller1"
    )
    seller.set_password("pass1234")
    seller.save()

    client = APIClient()
    response = client.post(
        "/api/auth/token/", {"username": "seller1", "password": "pass1234"}, format="json"
    )

    assert response.status_code == 200
    access_token = AccessToken(response.data["access"])
    assert access_token["role"] == UserProfile.Role.SELLER
    assert access_token["tenant_id"] == tenant.id
    assert access_token["branch_id"] == branch.id


@pytest.mark.django_db
def test_seller_me_endpoint_reflects_own_scope_only(make_user, make_tenant, make_branch):
    tenant_a = make_tenant("a")
    branch_a = make_branch(tenant_a, name="Branch A")
    tenant_b = make_tenant("b")
    make_branch(tenant_b, name="Branch B")

    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant_a, branch=branch_a)

    client = APIClient()
    client.force_authenticate(user=seller)
    response = client.get("/api/auth/me/")

    assert response.status_code == 200
    assert response.data["role"] == UserProfile.Role.SELLER
    assert response.data["tenant_id"] == tenant_a.id
    assert response.data["tenant_slug"] == "a"
    assert response.data["branch_id"] == branch_a.id
    assert response.data["tenant_id"] != tenant_b.id


@pytest.mark.django_db
def test_unassigned_user_gets_null_scope_from_me_endpoint(make_user):
    plain_user = make_user()  # auto-provisioned UNASSIGNED profile, no role assigned yet

    client = APIClient()
    client.force_authenticate(user=plain_user)
    response = client.get("/api/auth/me/")

    assert response.status_code == 200
    assert response.data["role"] == UserProfile.Role.UNASSIGNED
    assert response.data["tenant_id"] is None
