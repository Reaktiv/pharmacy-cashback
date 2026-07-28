from decimal import Decimal

import pytest

from apps.ledger.services import flag_transaction, post_earn_transaction


@pytest.mark.django_db
def test_flag_transaction_sets_flagged_true(
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
        idempotency_key="k1",
    )
    assert txn.flagged is False

    flagged_txn = flag_transaction(transaction_id=txn.pk)

    assert flagged_txn.flagged is True
    txn.refresh_from_db()
    assert txn.flagged is True
