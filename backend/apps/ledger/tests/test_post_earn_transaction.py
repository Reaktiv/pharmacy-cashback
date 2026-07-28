from decimal import Decimal

import pytest

from apps.ledger.models import Transaction
from apps.ledger.services import InsufficientBalanceError, get_balance, post_earn_transaction


@pytest.mark.django_db
def test_earn_transaction_creates_an_active_earn_row(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )

    assert txn.type == Transaction.Type.EARN
    assert txn.status == Transaction.Status.ACTIVE
    assert txn.cashback_earned == Decimal("10000.00")
    assert txn.cash_paid == Decimal("100000")


@pytest.mark.django_db
def test_no_cashback_checkbox_forces_zero_earned(
    make_tenant, make_branch, make_seller, make_customer
):
    """CLAUDE.md §2 rule 11: the prescription-only checkbox is the legal
    safety valve — it must force cashback_earned to exactly 0."""
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        no_cashback=True,
        idempotency_key="key-1",
    )

    assert txn.cashback_earned == Decimal("0.00")
    assert txn.no_cashback is True


@pytest.mark.django_db
def test_transaction_snapshots_the_rate_at_post_time(
    make_tenant, make_branch, make_seller, make_customer
):
    """CLAUDE.md §2 rule 5: rate changes affect only future transactions."""
    tenant = make_tenant("t", rate=Decimal("5.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )
    assert txn.cashback_rate == Decimal("5.00")
    assert txn.cashback_earned == Decimal("5000.00")

    tenant.cashback_rate = Decimal("10.00")
    tenant.save()

    txn.refresh_from_db()
    assert txn.cashback_rate == Decimal("5.00")  # untouched by the later rate change
    assert txn.cashback_earned == Decimal("5000.00")


@pytest.mark.django_db
def test_same_idempotency_key_returns_the_original_transaction_not_a_duplicate(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    first = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="same-key",
    )
    second = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="same-key",
    )

    assert first.pk == second.pk
    assert (
        Transaction.objects.all_tenants().filter(tenant=tenant, idempotency_key="same-key").count()
        == 1
    )
    assert get_balance(customer) == Decimal("10000.00")  # earned only once, not twice


@pytest.mark.django_db
def test_earn_and_spend_in_the_same_register_action(
    make_tenant, make_branch, make_seller, make_customer
):
    """§5: a type='earn' row may also carry a positive cashback_spent."""
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    # seed a balance to spend from
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="seed",
    )
    assert get_balance(customer) == Decimal("100000.00")

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        cashback_spent=Decimal("50000"),
        idempotency_key="combined",
    )

    assert txn.type == Transaction.Type.EARN
    assert txn.cashback_spent == Decimal("50000")
    assert txn.cash_paid == Decimal("50000")
    assert txn.cashback_earned == Decimal("5000.00")  # 10% of cash_paid (50000), not check_amount


@pytest.mark.django_db
def test_spending_more_than_the_balance_is_rejected(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    with pytest.raises(InsufficientBalanceError):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("100000"),
            cashback_spent=Decimal("1000"),  # customer has 0 balance
            idempotency_key="key-1",
        )
