from decimal import Decimal

import pytest

from apps.customers.models import PendingCashback
from apps.ledger.models import Transaction
from apps.ledger.services import get_balance, post_earn_by_phone


@pytest.mark.django_db
def test_earn_by_phone_posts_a_real_transaction_for_an_existing_customer(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant, phone="+998900000001")

    result = post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998900000001",
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )

    assert isinstance(result, Transaction)
    assert result.customer_id == customer.pk
    assert get_balance(customer) == Decimal("10000.00")


@pytest.mark.django_db
def test_earn_by_phone_with_no_existing_customer_creates_pending_cashback(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    result = post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998900009999",
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )

    assert isinstance(result, PendingCashback)
    assert result.phone == "+998900009999"
    assert result.amount == Decimal("10000.00")
    assert result.source_transaction is None
    assert result.claimed is False
    assert Transaction.objects.all_tenants().filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_earn_by_phone_no_cashback_and_no_customer_creates_nothing(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    result = post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998900009999",
        check_amount=Decimal("100000"),
        no_cashback=True,
        idempotency_key="key-1",
    )

    assert result is None
    assert PendingCashback.objects.all_tenants().filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_earn_by_phone_double_submit_for_new_phone_creates_only_one_pending_cashback(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    first = post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998900009999",
        check_amount=Decimal("100000"),
        idempotency_key="same-key",
    )
    second = post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998900009999",
        check_amount=Decimal("100000"),
        idempotency_key="same-key",
    )

    assert first.pk == second.pk
    assert PendingCashback.objects.all_tenants().filter(tenant=tenant).count() == 1
