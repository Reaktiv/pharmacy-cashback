from decimal import Decimal

from apps.ledger.services import calculate_earn, round_down_1000


def test_earn_is_calculated_from_cash_paid_not_check_amount():
    """CLAUDE.md §2 rule 2: cashback is earned only on the cash-paid portion,
    never on the cashback-paid portion (prevents an infinite growth loop:
    you can't earn cashback on money you didn't actually pay)."""
    check_amount = Decimal("100000")
    cash_paid = Decimal("50000")  # customer covered the other 50000 with points
    rate = Decimal("10.00")

    earned = calculate_earn(check_amount, cash_paid, rate)

    assert earned == round_down_1000(cash_paid * rate / Decimal("100"))
    assert earned != round_down_1000(check_amount * rate / Decimal("100"))


def test_earn_rounds_down_to_nearest_1000():
    earned = calculate_earn(
        check_amount=Decimal("100000"), cash_paid=Decimal("34567"), rate=Decimal("10.00")
    )
    # 34567 * 10% = 3456.70 -> rounds down to 3000
    assert earned == Decimal("3000.00")


def test_zero_cash_paid_earns_nothing():
    earned = calculate_earn(
        check_amount=Decimal("100000"), cash_paid=Decimal("0"), rate=Decimal("10.00")
    )
    assert earned == Decimal("0.00")
