from decimal import Decimal

import pytest

from apps.ledger.services import round_down_1000


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0"), Decimal("0.00")),
        (Decimal("999.99"), Decimal("0.00")),
        (Decimal("1000"), Decimal("1000.00")),
        (Decimal("1999.99"), Decimal("1000.00")),
        (Decimal("2000"), Decimal("2000.00")),
        (Decimal("12345.67"), Decimal("12000.00")),
        (Decimal("999999.99"), Decimal("999000.00")),
    ],
)
def test_round_down_1000(value, expected):
    assert round_down_1000(value) == expected


def test_round_down_1000_rejects_negative_values():
    with pytest.raises(ValueError):
        round_down_1000(Decimal("-1"))
