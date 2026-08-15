
import pytest
from django.contrib.auth.models import User

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
def test_branch_creation_blocked_once_limit_reached(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    tenant.branch_limit = 1
    tenant.save(update_fields=["branch_limit"])
    make_branch(tenant, name="Existing Branch")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/branches/", {"name": "Second Branch", "address": "x"}, format="json"
    )

    assert response.status_code == 400
    assert not Branch.objects.all_tenants().filter(tenant=tenant, name="Second Branch").exists()


@pytest.mark.django_db
def test_branch_creation_unlimited_when_limit_is_null(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    assert tenant.branch_limit is None
    for i in range(5):
        make_branch(tenant, name=f"Branch {i}")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/branches/", {"name": "One More Branch", "address": "x"}, format="json"
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_editing_an_existing_branch_is_not_blocked_by_the_limit(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    tenant.branch_limit = 1
    tenant.save(update_fields=["branch_limit"])
    branch = make_branch(tenant, name="Only Branch")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(
        f"/api/branches/{branch.id}/", {"name": "Renamed Branch"}, format="json"
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_only_superadmin_can_set_branch_limit(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"branch_limit": 3}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_superadmin_can_set_branch_limit(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.patch(
        f"/api/tenants/{tenant.id}/", {"branch_limit": 3}, format="json"
    )

    assert response.status_code == 200
    tenant.refresh_from_db()
    assert tenant.branch_limit == 3


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
def test_tenant_admin_can_delete_an_empty_branch(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.delete(f"/api/branches/{branch.id}/")

    assert response.status_code == 204
    assert not Branch.objects.all_tenants().filter(pk=branch.id).exists()


@pytest.mark.django_db
def test_deleting_a_branch_removes_its_sellers_and_branch_manager_logins(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    seller_user_id = seller.user_id
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.delete(f"/api/branches/{branch.id}/")

    assert response.status_code == 204
    assert not Branch.objects.all_tenants().filter(pk=branch.id).exists()
    assert not Seller.objects.all_tenants().filter(pk=seller.id).exists()
    assert not User.objects.filter(pk=seller_user_id).exists()
    assert not User.objects.filter(pk=manager.id).exists()


@pytest.mark.django_db
def test_deleting_a_branch_with_transaction_history_deletes_the_transactions_too(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    """Deleting a branch is a deliberate, double-confirmed action on the
    frontend (see ConfirmDialog usage in TenantAdminPage) — once it reaches
    the API it cascades fully, including ledger history and a reversal
    (Transaction.reverses is a self-referential PROTECT FK that must be
    cleared before the bulk delete, not just Transaction.branch)."""
    from decimal import Decimal

    from apps.ledger.models import Transaction
    from apps.ledger.services import post_earn_transaction, post_reversal

    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    post_reversal(original_txn=txn, actor=admin)
    client = api_client_for(admin)

    response = client.delete(f"/api/branches/{branch.id}/")

    assert response.status_code == 204
    assert Branch.objects.all_tenants().filter(pk=branch.id).count() == 0
    assert Transaction.objects.all_tenants().filter(branch=branch).count() == 0


@pytest.mark.django_db
def test_tenant_admin_cannot_delete_another_tenants_branch(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    branch_b = make_branch(tenant_b)
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.delete(f"/api/branches/{branch_b.id}/")

    assert response.status_code == 404
    assert Branch.objects.all_tenants().filter(pk=branch_b.id).exists()


@pytest.mark.django_db
def test_seller_cannot_manage_branches(api_client_for, make_user, make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)
    client = api_client_for(seller)

    response = client.get("/api/branches/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admin_cannot_create_a_seller(
    api_client_for, make_user, make_tenant, make_branch
):
    """CLAUDE.md §3: only the branch manager adds sellers now — the tenant
    admin's job is to provision branch managers (see BranchManagerViewSet
    tests below), not sellers directly."""
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

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admin_can_still_view_sellers_in_their_tenant(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    make_seller(tenant, branch)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.get("/api/sellers/")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1


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


@pytest.mark.django_db
def test_tenant_admin_can_create_a_branch_manager_with_login(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/branch-managers/",
        {"branch": branch.id, "username": "newmanager", "password": "somepass123"},
        format="json",
    )

    assert response.status_code == 201
    profile = UserProfile.objects.get(pk=response.data["id"])
    assert profile.tenant_id == tenant.id
    assert profile.branch_id == branch.id
    assert profile.role == UserProfile.Role.BRANCH_MANAGER
    assert profile.user.username == "newmanager"
    assert profile.user.check_password("somepass123")


@pytest.mark.django_db
def test_creating_a_branch_manager_for_another_tenants_branch_is_rejected(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    branch_b = make_branch(tenant_b)
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.post(
        "/api/branch-managers/",
        {"branch": branch_b.id, "username": "newmanager", "password": "somepass123"},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_branch_manager_cannot_create_a_branch_manager(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.post(
        "/api/branch-managers/",
        {"branch": branch.id, "username": "newmanager", "password": "somepass123"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admin_only_sees_their_own_branch_managers(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    branch_a = make_branch(tenant_a)
    branch_b = make_branch(tenant_b)
    make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant_a, branch=branch_a)
    make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant_b, branch=branch_b)
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.get("/api/branch-managers/")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    assert rows[0]["branch"] == branch_a.id


@pytest.mark.django_db
def test_tenant_admin_can_delete_a_branch_manager_and_the_login_is_gone(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    manager_user_id = manager.id
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.delete(f"/api/branch-managers/{manager.profile.id}/")

    assert response.status_code == 204
    assert not User.objects.filter(pk=manager_user_id).exists()
    assert not UserProfile.objects.filter(user_id=manager_user_id).exists()


@pytest.mark.django_db
def test_tenant_admin_cannot_delete_another_tenants_branch_manager(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    branch_b = make_branch(tenant_b)
    manager_b = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant_b, branch=branch_b)
    admin_a = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    client = api_client_for(admin_a)

    response = client.delete(f"/api/branch-managers/{manager_b.profile.id}/")

    assert response.status_code == 404
    assert User.objects.filter(pk=manager_b.id).exists()


@pytest.mark.django_db
def test_branch_manager_can_delete_their_own_branch_seller_and_the_login_is_gone(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    seller_user_id = seller.user_id
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.delete(f"/api/sellers/{seller.id}/")

    assert response.status_code == 204
    assert not Seller.objects.all_tenants().filter(pk=seller.id).exists()
    assert not User.objects.filter(pk=seller_user_id).exists()


@pytest.mark.django_db
def test_branch_manager_cannot_delete_a_seller_in_another_branch(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    seller_b = make_seller(tenant, branch_b)
    manager_a = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch_a)
    client = api_client_for(manager_a)

    response = client.delete(f"/api/sellers/{seller_b.id}/")

    assert response.status_code == 404
    assert Seller.objects.all_tenants().filter(pk=seller_b.id).exists()


@pytest.mark.django_db
def test_tenant_admin_cannot_delete_a_seller(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    """CLAUDE.md §3: only the branch manager manages (and so removes) sellers."""
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.delete(f"/api/sellers/{seller.id}/")

    assert response.status_code == 403
    assert Seller.objects.all_tenants().filter(pk=seller.id).exists()


@pytest.mark.django_db
def test_branch_manager_can_set_a_daily_limit_when_creating_a_seller(
    api_client_for, make_user, make_tenant, make_branch
):
    """CLAUDE.md §8: per-seller daily transaction limit is a fraud
    mitigation the branch manager sets — writable at creation time."""
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.post(
        "/api/sellers/",
        {
            "branch": branch.id,
            "phone": "+998900000099",
            "full_name": "New Seller",
            "username": "newseller",
            "password": "somepass123",
            "daily_txn_limit": 20,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["daily_txn_limit"] == 20
    seller = Seller.objects.all_tenants().get(pk=response.data["id"])
    assert seller.daily_txn_limit == 20


@pytest.mark.django_db
def test_branch_manager_can_update_a_sellers_daily_limit(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.patch(f"/api/sellers/{seller.id}/", {"daily_txn_limit": 5}, format="json")

    assert response.status_code == 200
    seller.refresh_from_db()
    assert seller.daily_txn_limit == 5

    # Clearing it back out (empty in the UI) must restore "unlimited", not
    # leave the previous number stuck.
    response = client.patch(f"/api/sellers/{seller.id}/", {"daily_txn_limit": None}, format="json")

    assert response.status_code == 200
    seller.refresh_from_db()
    assert seller.daily_txn_limit is None


@pytest.mark.django_db
def test_branch_manager_cannot_update_a_sellers_daily_limit_in_another_branch(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    seller_b = make_seller(tenant, branch_b)
    manager_a = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch_a)
    client = api_client_for(manager_a)

    response = client.patch(f"/api/sellers/{seller_b.id}/", {"daily_txn_limit": 5}, format="json")

    assert response.status_code == 404
    seller_b.refresh_from_db()
    assert seller_b.daily_txn_limit is None


@pytest.mark.django_db
def test_superadmin_can_create_a_tenant_admin_with_login(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.post(
        "/api/tenant-admins/",
        {"tenant": tenant.id, "username": "newadmin", "password": "somepass123"},
        format="json",
    )

    assert response.status_code == 201
    profile = UserProfile.objects.get(pk=response.data["id"])
    assert profile.tenant_id == tenant.id
    assert profile.branch_id is None
    assert profile.role == UserProfile.Role.TENANT_ADMIN
    assert profile.user.username == "newadmin"
    assert profile.user.check_password("somepass123")


@pytest.mark.django_db
def test_tenant_admin_cannot_create_a_tenant_admin(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.post(
        "/api/tenant-admins/",
        {"tenant": tenant.id, "username": "newadmin", "password": "somepass123"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admins_list_can_be_filtered_by_tenant(api_client_for, make_user, make_tenant):
    tenant_a = make_tenant("a")
    tenant_b = make_tenant("b")
    make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_a)
    make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant_b)
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.get(f"/api/tenant-admins/?tenant={tenant_a.id}")

    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    assert rows[0]["tenant"] == tenant_a.id


@pytest.mark.django_db
def test_superadmin_can_delete_a_tenant_admin_and_the_login_is_gone(
    api_client_for, make_user, make_tenant
):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    admin_user_id = admin.id
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.delete(f"/api/tenant-admins/{admin.profile.id}/")

    assert response.status_code == 204
    assert not User.objects.filter(pk=admin_user_id).exists()
    assert not UserProfile.objects.filter(user_id=admin_user_id).exists()
