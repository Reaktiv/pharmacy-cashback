from decimal import Decimal

import pytest

from apps.ledger.models import Transaction
from apps.ledger.services import get_balance, post_earn_transaction, post_reversal


@pytest.mark.django_db
def test_reversal_undoes_an_earn_transactions_effect_on_balance(
    make_tenant, make_branch, make_seller, make_customer, make_user
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user()

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )
    assert get_balance(customer) == Decimal("10000.00")

    post_reversal(original_txn=txn, actor=manager)

    assert get_balance(customer) == Decimal("0.00")


@pytest.mark.django_db
def test_reversal_marks_the_original_as_reversed(
    make_tenant, make_branch, make_seller, make_customer, make_user
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user()

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )

    reversal = post_reversal(original_txn=txn, actor=manager)

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.REVERSED
    assert reversal.status == Transaction.Status.ACTIVE
    assert reversal.type == Transaction.Type.REVERSAL
    assert reversal.reverses_id == txn.pk


@pytest.mark.django_db
def test_reversal_swaps_earned_and_spent_to_stay_non_negative(
    make_tenant, make_branch, make_seller, make_customer, make_user
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user()

    # seed a balance, then earn+spend in one action
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="seed",
    )
    combined = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        cashback_spent=Decimal("50000"),
        idempotency_key="combined",
    )
    balance_before = get_balance(customer)

    reversal = post_reversal(original_txn=combined, actor=manager)

    assert reversal.cashback_earned == combined.cashback_spent
    assert reversal.cashback_spent == combined.cashback_earned
    assert reversal.cashback_earned >= 0
    assert reversal.cashback_spent >= 0
    # net effect: the combined txn's (earned - spent) contribution is undone
    expected_after = balance_before - (combined.cashback_earned - combined.cashback_spent)
    assert get_balance(customer) == expected_after


@pytest.mark.django_db
def test_double_reversal_is_rejected(
    make_tenant, make_branch, make_seller, make_customer, make_user
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    manager = make_user()

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="key-1",
    )

    post_reversal(original_txn=txn, actor=manager)

    with pytest.raises(ValueError):
        post_reversal(original_txn=txn, actor=manager)
