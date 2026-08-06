from decimal import Decimal

from apps.ledger.services import calculate_earn, round_down_som


def test_earn_is_calculated_from_cash_paid_not_check_amount():
    """CLAUDE.md §2 rule 2: cashback is earned only on the cash-paid portion,
    never on the cashback-paid portion (prevents an infinite growth loop:
    you can't earn cashback on money you didn't actually pay)."""
    check_amount = Decimal("100000")
    cash_paid = Decimal("50000")  # customer covered the other 50000 with points
    rate = Decimal("10.00")

    earned = calculate_earn(check_amount, cash_paid, rate)

    assert earned == round_down_som(cash_paid * rate / Decimal("100"))
    assert earned != round_down_som(check_amount * rate / Decimal("100"))


def test_earn_rounds_down_to_nearest_som():
    earned = calculate_earn(
        check_amount=Decimal("100000"), cash_paid=Decimal("34567"), rate=Decimal("10.00")
    )
    # 34567 * 10% = 3456.70 -> rounds down to 3456
    assert earned == Decimal("3456.00")


def test_zero_cash_paid_earns_nothing():
    earned = calculate_earn(
        check_amount=Decimal("100000"), cash_paid=Decimal("0"), rate=Decimal("10.00")
    )
    assert earned == Decimal("0.00")


def test_small_rate_still_earns_cashback():
    """Regression: with the old round-down-to-1000 rule, a 0.1% rate never
    earned anything below a ~1,000,000 cash_paid check. Rounding to the
    nearest whole so'm instead keeps sub-1% rates meaningful."""
    earned = calculate_earn(
        check_amount=Decimal("50000"), cash_paid=Decimal("50000"), rate=Decimal("0.10")
    )
    # 50000 * 0.1% = 50.00
    assert earned == Decimal("50.00")


def test_very_small_rate_still_earns_cashback():
    earned = calculate_earn(
        check_amount=Decimal("50000"), cash_paid=Decimal("50000"), rate=Decimal("0.01")
    )
    # 50000 * 0.01% = 5.00
    assert earned == Decimal("5.00")
