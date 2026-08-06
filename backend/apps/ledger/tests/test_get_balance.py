from decimal import Decimal

import pytest

from apps.ledger.services import get_balance, post_earn_transaction, post_reversal


@pytest.mark.django_db
def test_balance_is_always_exactly_the_hand_computed_ledger_sum(
    make_tenant, make_branch, make_seller, make_customer, make_user
):
    """CLAUDE.md §2 rule 6: balance is never a stored column — it's always
    SUM(earned) - SUM(spent) over the ledger. This test builds up a mixed
    history (earn, combined earn+spend, reversal) and checks get_balance()
    against numbers computed by hand, not by re-using get_balance's own
    aggregation logic.
    """
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user()

    # 1) earn 10000 on a 100000 check
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="txn-1",
    )
    # running total: +10000
    assert get_balance(customer) == Decimal("10000.00")

    # 2) earn 20000 on a 200000 check
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("200000"),
        idempotency_key="txn-2",
    )
    # running total: +10000 +20000 = 30000
    assert get_balance(customer) == Decimal("30000.00")

    # 3) spend 15000 of it on a 50000 check (also earns 10% of the 35000 cash
    # paid = 3500 exactly, no rounding needed since it's already a whole som)
    txn3 = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("50000"),
        cashback_spent=Decimal("15000"),
        idempotency_key="txn-3",
    )
    assert txn3.cashback_earned == Decimal("3500.00")  # round_down_som(10% of cash_paid=35000)
    # running total: 30000 - 15000 + 3500 = 18500
    assert get_balance(customer) == Decimal("18500.00")

    # 4) reverse transaction #3
    post_reversal(original_txn=txn3, actor=manager)
    # reversing txn3 undoes its net (+3500 - 15000 = -11500) contribution:
    # 18500 - (-11500) = 30000
    assert get_balance(customer) == Decimal("30000.00")


@pytest.mark.django_db
def test_new_customer_has_zero_balance(make_tenant, make_customer):
    tenant = make_tenant("t")
    customer = make_customer(tenant)
    assert get_balance(customer) == Decimal("0")


@pytest.mark.django_db
def test_balance_is_per_customer_not_shared_across_the_tenant(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer_a = make_customer(tenant, phone="+998900000001")
    customer_b = make_customer(tenant, phone="+998900000002")

    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer_a,
        check_amount=Decimal("100000"),
        idempotency_key="txn-a",
    )

    assert get_balance(customer_a) == Decimal("10000.00")
    assert get_balance(customer_b) == Decimal("0")
