from decimal import Decimal

import pytest

from apps.ledger.services import calculate_redemption
from apps.tenants.models import GlobalSettings


@pytest.mark.django_db
def test_redemption_is_capped_at_50_percent_of_check(make_tenant):
    """CLAUDE.md §2 rule 3: redemption capped at 50% of the check total —
    the customer must always pay at least half in cash."""
    tenant = make_tenant("t")
    GlobalSettings.load()  # default max_redeem_percent = 50.00

    allowed = calculate_redemption(
        check_amount=Decimal("100000"),
        requested=Decimal("100000"),  # customer asks to pay the whole thing in points
        customer_balance=Decimal("1000000"),  # and has plenty of balance
        tenant=tenant,
    )

    assert allowed == Decimal("50000.00")


@pytest.mark.django_db
def test_redemption_never_exceeds_customer_balance(make_tenant):
    tenant = make_tenant("t")
    GlobalSettings.load()

    allowed = calculate_redemption(
        check_amount=Decimal("100000"),
        requested=Decimal("100000"),
        customer_balance=Decimal("3456"),  # far below the 50% cap
        tenant=tenant,
    )

    assert allowed == Decimal("3456.00")  # balance-limited, rounded down to whole som


@pytest.mark.django_db
def test_redemption_never_exceeds_the_requested_amount(make_tenant):
    tenant = make_tenant("t")
    GlobalSettings.load()

    allowed = calculate_redemption(
        check_amount=Decimal("100000"),
        requested=Decimal("5000"),  # customer only wants to spend 5000
        customer_balance=Decimal("1000000"),
        tenant=tenant,
    )

    assert allowed == Decimal("5000.00")


@pytest.mark.django_db
def test_below_minimum_check_amount_cannot_redeem_at_all(make_tenant):
    """CLAUDE.md §2 rule 8: below the tenant's minimum check amount, points
    can be earned but not spent."""
    tenant = make_tenant("t")
    tenant.min_redeem_amount = Decimal("20000.00")
    tenant.save()
    GlobalSettings.load()

    allowed = calculate_redemption(
        check_amount=Decimal("10000"),  # below the 20000 minimum
        requested=Decimal("5000"),
        customer_balance=Decimal("1000000"),  # even with plenty of balance
        tenant=tenant,
    )

    assert allowed == Decimal("0")


@pytest.mark.django_db
def test_at_exactly_the_minimum_check_amount_redemption_is_allowed(make_tenant):
    tenant = make_tenant("t")
    tenant.min_redeem_amount = Decimal("20000.00")
    tenant.save()
    GlobalSettings.load()

    allowed = calculate_redemption(
        check_amount=Decimal("20000"),
        requested=Decimal("5000"),
        customer_balance=Decimal("1000000"),
        tenant=tenant,
    )

    assert allowed == Decimal("5000.00")
