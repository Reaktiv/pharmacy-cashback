"""The mandatory tenant-isolation test (CLAUDE.md §4), now with the real
models it's actually named after. apps/tenants/tests/test_isolation.py
proved the TenantScopedModel/TenantManager mechanism itself with dummy
models back in Phase 1, before Customer/Transaction/Branch/Seller existed;
this is the follow-up promised then.
"""

from decimal import Decimal

import pytest

from apps.accounts.models import Branch, Seller
from apps.customers.models import Customer
from apps.ledger.models import Transaction
from apps.ledger.services import post_earn_transaction
from apps.tenants.context import reset_current_tenant, set_current_tenant


@pytest.fixture
def two_tenants_with_data(make_tenant, make_branch, make_seller, make_customer):
    tenant_a = make_tenant("tenant-a", rate=Decimal("5.00"))
    branch_a = make_branch(tenant_a, name="Branch A")
    seller_a = make_seller(tenant_a, branch_a)
    customer_a = make_customer(tenant_a, phone="+998901000001")
    post_earn_transaction(
        tenant=tenant_a,
        branch=branch_a,
        seller=seller_a,
        customer=customer_a,
        check_amount=Decimal("100000"),
        idempotency_key="a-1",
    )

    tenant_b = make_tenant("tenant-b", rate=Decimal("5.00"))
    branch_b = make_branch(tenant_b, name="Branch B")
    seller_b = make_seller(tenant_b, branch_b)
    customer_b = make_customer(tenant_b, phone="+998902000001")
    post_earn_transaction(
        tenant=tenant_b,
        branch=branch_b,
        seller=seller_b,
        customer=customer_b,
        check_amount=Decimal("100000"),
        idempotency_key="b-1",
    )

    return tenant_a, tenant_b


@pytest.mark.django_db
def test_tenant_a_admin_cannot_read_tenant_b_data(two_tenants_with_data):
    tenant_a, tenant_b = two_tenants_with_data

    token = set_current_tenant(tenant_a)
    try:
        branches = list(Branch.objects.all())
        sellers = list(Seller.objects.all())
        customers = list(Customer.objects.all())
        transactions = list(Transaction.objects.all())
    finally:
        reset_current_tenant(token)

    for row in (*branches, *sellers, *customers, *transactions):
        assert row.tenant_id == tenant_a.id
        assert row.tenant_id != tenant_b.id

    assert len(branches) == 1
    assert len(sellers) == 1
    assert len(customers) == 1
    assert len(transactions) == 1


@pytest.mark.django_db
def test_tenant_b_admin_cannot_read_tenant_a_data(two_tenants_with_data):
    tenant_a, tenant_b = two_tenants_with_data

    token = set_current_tenant(tenant_b)
    try:
        branches = list(Branch.objects.all())
        sellers = list(Seller.objects.all())
        customers = list(Customer.objects.all())
        transactions = list(Transaction.objects.all())
    finally:
        reset_current_tenant(token)

    for row in (*branches, *sellers, *customers, *transactions):
        assert row.tenant_id == tenant_b.id
        assert row.tenant_id != tenant_a.id
