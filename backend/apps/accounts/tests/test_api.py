
import pytest

from apps.accounts.models import Branch, Seller, UserProfile


@pytest.mark.django_db
def test_tenant_admin_can_create_a_branch(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/branches/", {"name": "New Branch", "address": "123 Main St"}, format="json"
    )

    assert response.status_code == 201
    branch = Branch.objects.all_tenants().get(pk=response.data["id"])
    assert branch.tenant_id == tenant.id


@pytest.mark.django_db
def test_tenant_admin_only_sees_their_own_branches(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    make_branch(tenant_a, name="A Branch")
    make_branch(tenant_b, name="B Branch")
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.get("/api/branches/")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    assert rows[0]["name"] == "A Branch"


@pytest.mark.django_db
def test_seller_cannot_manage_branches(api_client_for, make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)
    client = api_client_for(seller)

    response = client.get("/api/branches/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admin_can_create_a_seller_with_login(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/sellers/",
        {
            "branch": branch.id,
            "phone": "+998900000099",
            "full_name": "New Seller",
            "username": "newseller",
            "password": "somepass123",
        },
        format="json",
    )

    assert response.status_code == 201
    seller = Seller.objects.all_tenants().get(pk=response.data["id"])
    assert seller.tenant_id == tenant.id
    assert seller.user.username == "newseller"
    assert seller.user.profile.role == UserProfile.Role.SELLER
    assert seller.user.profile.branch_id == branch.id
    assert seller.user.check_password("somepass123")


@pytest.mark.django_db
def test_creating_a_seller_for_another_tenants_branch_is_rejected(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    branch_b = make_branch(tenant_b)
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.post(
        "/api/sellers/",
        {
            "branch": branch_b.id,
            "phone": "+998900000099",
            "full_name": "New Seller",
            "username": "newseller",
            "password": "somepass123",
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_branch_manager_only_sees_own_branch_sellers(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    make_seller(tenant, branch_a)
    make_seller(tenant, branch_b)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch_a)
    client = api_client_for(manager)

    response = client.get("/api/sellers/")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    assert rows[0]["branch"] == branch_a.id


@pytest.mark.django_db
def test_branch_manager_cannot_create_a_seller_in_another_branch(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch_a)
    client = api_client_for(manager)

    response = client.post(
        "/api/sellers/",
        {
            "branch": branch_b.id,
            "phone": "+998900000099",
            "full_name": "New Seller",
            "username": "newseller",
            "password": "somepass123",
        },
        format="json",
    )

    assert response.status_code == 400
