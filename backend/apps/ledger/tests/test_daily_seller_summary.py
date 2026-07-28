from decimal import Decimal

import pytest

from apps.ledger.services import get_daily_seller_summary, post_earn_transaction
from apps.ledger.tasks import send_daily_seller_summaries


@pytest.mark.django_db
def test_daily_seller_summary_aggregates_per_seller(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller_a = make_seller(tenant, branch)
    seller_b = make_seller(tenant, branch)
    customer = make_customer(tenant)

    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller_a,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="a1",
    )
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller_a,
        customer=customer,
        check_amount=Decimal("200000"),
        idempotency_key="a2",
    )
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller_b,
        customer=customer,
        check_amount=Decimal("50000"),
        idempotency_key="b1",
    )

    summary = get_daily_seller_summary(branch=branch)
    by_seller = {row["seller"].pk: row for row in summary}

    assert by_seller[seller_a.pk]["txn_count"] == 2
    assert by_seller[seller_a.pk]["avg_check"] == Decimal("150000")
    assert by_seller[seller_a.pk]["total_earned"] == Decimal("30000.00")

    assert by_seller[seller_b.pk]["txn_count"] == 1
    assert by_seller[seller_b.pk]["total_earned"] == Decimal("5000.00")


@pytest.mark.django_db
def test_daily_seller_summary_excludes_other_branches(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    seller_a = make_seller(tenant, branch_a)
    customer = make_customer(tenant)

    post_earn_transaction(
        tenant=tenant,
        branch=branch_a,
        seller=seller_a,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="a1",
    )

    assert get_daily_seller_summary(branch=branch_b) == []


@pytest.mark.django_db
def test_empty_branch_returns_empty_summary(make_tenant, make_branch):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    assert get_daily_seller_summary(branch=branch) == []


@pytest.mark.django_db
def test_send_daily_seller_summaries_task_runs_without_error(
    make_tenant, make_branch, make_seller, make_customer
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

    send_daily_seller_summaries()  # must not raise
