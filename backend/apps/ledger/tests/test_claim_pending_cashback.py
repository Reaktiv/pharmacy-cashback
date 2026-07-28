from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.customers.models import PendingCashback
from apps.ledger.models import Transaction
from apps.ledger.services import claim_pending_cashback, get_balance, post_earn_by_phone


@pytest.mark.django_db
def test_claim_moves_pending_cashback_into_a_real_earn_transaction(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    pending = post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998900000001",
        check_amount=Decimal("100000"),
        idempotency_key="pre-registration",
    )
    assert isinstance(pending, PendingCashback)

    customer = make_customer(tenant, phone="+998900000001")
    claimed = claim_pending_cashback(customer=customer)

    assert len(claimed) == 1
    txn = claimed[0]
    assert txn.type == Transaction.Type.EARN
    assert txn.cashback_earned == pending.amount
    assert txn.branch_id == branch.pk
    assert get_balance(customer) == pending.amount

    pending.refresh_from_db()
    assert pending.claimed is True
    assert pending.source_transaction_id == txn.pk


@pytest.mark.django_db
def test_claim_moves_multiple_pending_rows_from_different_branches(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch_a = make_branch(tenant, name="Branch A")
    branch_b = make_branch(tenant, name="Branch B")
    seller_a = make_seller(tenant, branch_a)
    seller_b = make_seller(tenant, branch_b)

    post_earn_by_phone(
        tenant=tenant,
        branch=branch_a,
        seller=seller_a,
        phone="+998900000001",
        check_amount=Decimal("100000"),
        idempotency_key="first",
    )
    post_earn_by_phone(
        tenant=tenant,
        branch=branch_b,
        seller=seller_b,
        phone="+998900000001",
        check_amount=Decimal("50000"),
        idempotency_key="second",
    )

    customer = make_customer(tenant, phone="+998900000001")
    claimed = claim_pending_cashback(customer=customer)

    assert len(claimed) == 2
    branches_used = {txn.branch_id for txn in claimed}
    assert branches_used == {branch_a.pk, branch_b.pk}
    assert get_balance(customer) == Decimal("10000.00") + Decimal("5000.00")


@pytest.mark.django_db
def test_claim_skips_expired_pending_cashback(make_tenant, make_branch, make_customer):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    customer = make_customer(tenant, phone="+998900000001")

    PendingCashback.objects.all_tenants().create(
        tenant=tenant,
        phone="+998900000001",
        amount=Decimal("5000"),
        branch=branch,
        expires_at=timezone.now() - timedelta(days=1),
    )

    claimed = claim_pending_cashback(customer=customer)

    assert claimed == []
    assert get_balance(customer) == Decimal("0")


@pytest.mark.django_db
def test_claim_skips_already_claimed_pending_cashback(make_tenant, make_branch, make_customer):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    customer = make_customer(tenant, phone="+998900000001")

    PendingCashback.objects.all_tenants().create(
        tenant=tenant,
        phone="+998900000001",
        amount=Decimal("5000"),
        branch=branch,
        claimed=True,
    )

    claimed = claim_pending_cashback(customer=customer)

    assert claimed == []


@pytest.mark.django_db
def test_claim_only_matches_pending_cashback_for_the_same_phone(
    make_tenant, make_branch, make_customer
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    customer = make_customer(tenant, phone="+998900000001")

    PendingCashback.objects.all_tenants().create(
        tenant=tenant, phone="+998900099999", amount=Decimal("5000"), branch=branch
    )

    claimed = claim_pending_cashback(customer=customer)

    assert claimed == []
