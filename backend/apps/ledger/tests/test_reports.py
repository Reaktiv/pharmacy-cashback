from decimal import Decimal

import pytest

from apps.ledger.reports import (
    get_branch_report,
    get_cross_tenant_dashboard,
    get_daily_earn_spend_report,
    get_seller_report,
    get_seller_transactions,
    get_total_liability,
)
from apps.ledger.services import post_earn_transaction, post_reversal
from apps.tenants.models import Bot


@pytest.mark.django_db
def test_total_liability_matches_hand_computed_sum(
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
        idempotency_key="a1",
    )
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer_b,
        check_amount=Decimal("50000"),
        idempotency_key="b1",
    )

    assert get_total_liability(tenant=tenant) == Decimal("10000.00") + Decimal("5000.00")


@pytest.mark.django_db
def test_total_liability_scoped_to_tenant(make_tenant, make_branch, make_seller, make_customer):
    tenant_a = make_tenant("a", rate=Decimal("10.00"))
    branch_a = make_branch(tenant_a)
    seller_a = make_seller(tenant_a, branch_a)
    customer_a = make_customer(tenant_a)
    post_earn_transaction(
        tenant=tenant_a,
        branch=branch_a,
        seller=seller_a,
        customer=customer_a,
        check_amount=Decimal("100000"),
        idempotency_key="a1",
    )

    tenant_b = make_tenant("b", rate=Decimal("10.00"))
    assert get_total_liability(tenant=tenant_b) == Decimal("0")
    assert get_total_liability(tenant=tenant_a) == Decimal("10000.00")


@pytest.mark.django_db
def test_total_liability_across_all_tenants_when_unscoped(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant_a = make_tenant("a", rate=Decimal("10.00"))
    branch_a = make_branch(tenant_a)
    seller_a = make_seller(tenant_a, branch_a)
    customer_a = make_customer(tenant_a)
    post_earn_transaction(
        tenant=tenant_a,
        branch=branch_a,
        seller=seller_a,
        customer=customer_a,
        check_amount=Decimal("100000"),
        idempotency_key="a1",
    )

    tenant_b = make_tenant("b", rate=Decimal("10.00"))
    branch_b = make_branch(tenant_b)
    seller_b = make_seller(tenant_b, branch_b)
    customer_b = make_customer(tenant_b)
    post_earn_transaction(
        tenant=tenant_b,
        branch=branch_b,
        seller=seller_b,
        customer=customer_b,
        check_amount=Decimal("50000"),
        idempotency_key="b1",
    )

    assert get_total_liability() == Decimal("10000.00") + Decimal("5000.00")


@pytest.mark.django_db
def test_cross_tenant_dashboard_reports_customers_and_liability(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    customer.telegram_id = 1
    customer.save(update_fields=["telegram_id"])
    Bot.objects.all_tenants().create(tenant=tenant, username="@bot", is_active=True)
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    rows = get_cross_tenant_dashboard()
    row = next(r for r in rows if r["tenant"].pk == tenant.pk)

    assert row["customers"] == 1
    assert row["active_30d"] == 1
    assert row["today_txns"] == 1
    assert row["total_liability"] == Decimal("10000.00")
    assert row["status"] == "active"
    assert row["bot"].username == "@bot"


@pytest.mark.django_db
def test_cross_tenant_dashboard_status_inactive_without_bot(make_tenant):
    tenant = make_tenant("t")
    rows = get_cross_tenant_dashboard()
    row = next(r for r in rows if r["tenant"].pk == tenant.pk)
    assert row["status"] == "inactive"
    assert row["bot"] is None


@pytest.mark.django_db
def test_cross_tenant_dashboard_query_count_does_not_scale_with_tenant_count(
    django_assert_num_queries, make_tenant, make_branch, make_seller, make_customer
):
    """get_cross_tenant_dashboard() must stay at a flat number of queries as
    tenants are added — it batches each metric into one GROUP BY tenant_id
    query instead of looping per tenant, so N tenants shouldn't cost more
    queries than 1 tenant."""

    def _seed_tenant(slug):
        tenant = make_tenant(slug, rate=Decimal("10.00"))
        branch = make_branch(tenant)
        seller = make_seller(tenant, branch)
        customer = make_customer(tenant, phone=f"+99890000{slug}00")
        Bot.objects.all_tenants().create(tenant=tenant, username=f"@{slug}_bot", is_active=True)
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("100000"),
            idempotency_key=f"{slug}-1",
        )

    _seed_tenant("0001")

    with django_assert_num_queries(6):
        rows = get_cross_tenant_dashboard()
    assert len(rows) == 1

    _seed_tenant("0002")
    _seed_tenant("0003")

    with django_assert_num_queries(6):
        rows = get_cross_tenant_dashboard()
    assert len(rows) == 3


@pytest.mark.django_db
def test_branch_report_computes_outstanding_per_branch(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch_a = make_branch(tenant, name="A")
    branch_b = make_branch(tenant, name="B")
    seller_a = make_seller(tenant, branch_a)
    seller_b = make_seller(tenant, branch_b)
    customer = make_customer(tenant)

    txn_a = post_earn_transaction(
        tenant=tenant,
        branch=branch_a,
        seller=seller_a,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="a1",
    )
    post_earn_transaction(
        tenant=tenant,
        branch=branch_b,
        seller=seller_b,
        customer=customer,
        check_amount=Decimal("50000"),
        idempotency_key="b1",
    )
    post_reversal(original_txn=txn_a, actor=None)

    rows = {row["branch"].pk: row for row in get_branch_report(tenant=tenant)}

    assert rows[branch_a.pk]["outstanding"] == Decimal("0.00")  # earned then fully reversed
    assert rows[branch_b.pk]["outstanding"] == Decimal("5000.00")


@pytest.mark.django_db
def test_seller_report_counts_txns_and_flags(
    make_tenant, make_branch, make_seller, make_customer
):
    from apps.ledger.services import flag_transaction

    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    txn1 = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("200000"),
        idempotency_key="k2",
    )
    flag_transaction(transaction_id=txn1.pk)

    rows = get_seller_report(tenant=tenant)
    row = next(r for r in rows if r["seller"].pk == seller.pk)

    assert row["txn_count"] == 2
    assert row["avg_check"] == Decimal("150000")
    assert row["flagged_count"] == 1


@pytest.mark.django_db
def test_seller_transactions_returns_full_history_newest_first(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    other_seller = make_seller(tenant, branch)
    customer = make_customer(tenant, phone="+998900000009")

    txn1 = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    txn2 = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("200000"),
        idempotency_key="k2",
    )
    # A transaction by a different seller must not show up in this seller's history.
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=other_seller,
        customer=customer,
        check_amount=Decimal("300000"),
        idempotency_key="k3",
    )

    page = get_seller_transactions(tenant=tenant, seller_id=seller.pk)

    assert [row.pk for row in page.results] == [txn2.pk, txn1.pk]
    assert page.results[0].customer.phone == "+998900000009"
    assert page.count == 2


@pytest.mark.django_db
def test_seller_transactions_page_totals_cover_full_history_not_just_the_page(
    make_tenant, make_branch, make_seller, make_customer
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

    page = get_seller_transactions(tenant=tenant, seller_id=seller.pk, limit=1, offset=0)

    assert len(page.results) == 1
    assert page.count == 3
    assert page.total_cashback_earned == Decimal("30000.00")
    assert page.total_check_amount == Decimal("300000.00")


@pytest.mark.django_db
def test_daily_earn_spend_report_groups_by_day(
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

    rows = get_daily_earn_spend_report(tenant=tenant, days=7)

    assert len(rows) == 1
    assert rows[0]["total_earned"] == Decimal("10000.00")
    assert rows[0]["total_spent"] == Decimal("0")
