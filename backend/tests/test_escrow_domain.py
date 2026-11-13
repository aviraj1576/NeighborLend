"""Deterministic financial invariants; all databases are isolated."""

from decimal import Decimal

import pytest

from app.services.escrow_service import balanced_lines, paise


@pytest.mark.parametrize("value,expected", [("1.005", 101), (200, 20000), (Decimal("0"), 0)])
def test_money_conversion_is_decimal_half_up(value, expected):
    assert paise(value) == expected


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", -1, "100000000000"])
def test_invalid_financial_amounts_rejected(value):
    with pytest.raises(ValueError):
        paise(value)


def test_real_double_entry_balance_and_positive_lines():
    assert (
        balanced_lines(
            [("cash", "DEBIT", 90000), ("rent", "CREDIT", 40000), ("deposit", "CREDIT", 50000)]
        )
        == 90000
    )
    for lines in (
        [("cash", "DEBIT", 1)],
        [("cash", "CREDIT", -1)],
        [("a", "DEBIT", True), ("b", "CREDIT", 1)],
    ):
        with pytest.raises(ValueError):
            balanced_lines(lines)
