from decimal import Decimal

import pytest

from apps.accounts.models import UserProfile
from apps.ledger.models import Transaction
from apps.ledger.services import post_earn_transaction


@pytest.mark.django_db
def test_branch_manager_can_reverse_a_transaction_in_their_branch(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    client = api_client_for(manager)

    response = client.post("/api/reversals/", {"transaction_id": txn.pk}, format="json")

    assert response.status_code == 201
    txn.refresh_from_db()
    assert txn.status == Transaction.Status.REVERSED


@pytest.mark.django_db
def test_branch_manager_cannot_reverse_a_transaction_in_another_branch(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    seller_b = make_seller(tenant, branch_b)
    customer = make_customer(tenant)
    manager_a = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch_a)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch_b,
        seller=seller_b,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    client = api_client_for(manager_a)

    response = client.post("/api/reversals/", {"transaction_id": txn.pk}, format="json")

    assert response.status_code == 404
    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ACTIVE


@pytest.mark.django_db
def test_seller_cannot_issue_reversals(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    seller_user = make_user(role=UserProfile.Role.SELLER, tenant=tenant, branch=branch)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    client = api_client_for(seller_user)

    response = client.post("/api/reversals/", {"transaction_id": txn.pk}, format="json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_double_reversal_via_api_returns_a_clear_error(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    client = api_client_for(manager)
    client.post("/api/reversals/", {"transaction_id": txn.pk}, format="json")

    response = client.post("/api/reversals/", {"transaction_id": txn.pk}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_superadmin_can_view_cross_tenant_report(api_client_for, make_user, make_tenant):
    make_tenant("t")
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.get("/api/reports/cross-tenant/")

    assert response.status_code == 200
    assert isinstance(response.data, list)


@pytest.mark.django_db
def test_tenant_admin_cannot_view_cross_tenant_report(api_client_for, make_user, make_tenant):
    tenant = make_tenant("t")
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    response = client.get("/api/reports/cross-tenant/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_admin_can_view_branch_and_daily_reports(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    admin = make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant)
    client = api_client_for(admin)

    branch_response = client.get("/api/reports/branches/")
    daily_response = client.get("/api/reports/daily/?days=7")
    seller_response = client.get("/api/reports/sellers/")

    assert branch_response.status_code == 200
    assert branch_response.data[0]["outstanding"] == Decimal("10000.00")
    assert daily_response.status_code == 200
    assert len(daily_response.data) == 1
    assert seller_response.status_code == 200
    assert seller_response.data[0]["txn_count"] == 1


@pytest.mark.django_db
def test_superadmin_can_drill_into_a_specific_tenants_branch_report(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.get(f"/api/reports/branches/?tenant_id={tenant.id}")

    assert response.status_code == 200
    assert response.data[0]["outstanding"] == Decimal("10000.00")


@pytest.mark.django_db
def test_superadmin_report_without_tenant_id_is_rejected(api_client_for, make_user):
    superadmin = make_user(role=UserProfile.Role.SUPERADMIN)
    client = api_client_for(superadmin)

    response = client.get("/api/reports/branches/")

    assert response.status_code == 400


@pytest.mark.django_db
def test_branch_manager_can_view_their_own_sellers_transaction_history(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant, phone="+998900000001")
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.get(f"/api/reports/seller-transactions/?seller_id={seller.pk}")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["customer_phone"] == "+998900000001"
    assert response.data["results"][0]["cashback_earned"] == Decimal("10000.00")
    assert response.data["totals"]["cashback_earned"] == Decimal("10000.00")


@pytest.mark.django_db
def test_branch_manager_cannot_view_another_branchs_seller_transaction_history(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch_a = make_branch(tenant)
    branch_b = make_branch(tenant)
    seller_b = make_seller(tenant, branch_b)
    customer = make_customer(tenant)
    post_earn_transaction(
        tenant=tenant,
        branch=branch_b,
        seller=seller_b,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    manager_a = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch_a)
    client = api_client_for(manager_a)

    response = client.get(f"/api/reports/seller-transactions/?seller_id={seller_b.pk}")

    assert response.status_code == 404


@pytest.mark.django_db
def test_seller_transactions_are_paginated_with_accurate_totals(
    api_client_for, make_user, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    for i in range(3):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("100000"),
            idempotency_key=f"k{i}",
        )
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.get(
        f"/api/reports/seller-transactions/?seller_id={seller.pk}&limit=2&offset=0"
    )

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert len(response.data["results"]) == 2
    # Totals reflect all 3 transactions, not just the 2 returned on this page.
    assert response.data["totals"]["cashback_earned"] == Decimal("30000.00")

    next_page = client.get(
        f"/api/reports/seller-transactions/?seller_id={seller.pk}&limit=2&offset=2"
    )
    assert len(next_page.data["results"]) == 1


@pytest.mark.django_db
def test_seller_transactions_rejects_out_of_range_limit(
    api_client_for, make_user, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.get(f"/api/reports/seller-transactions/?seller_id={seller.pk}&limit=9999")

    assert response.status_code == 400


@pytest.mark.django_db
def test_seller_transactions_requires_seller_id(
    api_client_for, make_user, make_tenant, make_branch
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    manager = make_user(role=UserProfile.Role.BRANCH_MANAGER, tenant=tenant, branch=branch)
    client = api_client_for(manager)

    response = client.get("/api/reports/seller-transactions/")

    assert response.status_code == 400
