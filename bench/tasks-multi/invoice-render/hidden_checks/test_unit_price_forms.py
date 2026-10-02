from decimal import Decimal

import pytest
from models import LineItem, compute_totals, line_total


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("2.50", Decimal("2.50")),
        ("2", Decimal("2")),
        (3, Decimal("3")),
        (Decimal("0.99"), Decimal("0.99")),
        ("0", Decimal("0")),
        (0, Decimal("0")),
        ("1.500", Decimal("1.5")),
        ("1000000.01", Decimal("1000000.01")),
    ],
)
def test_valid_unit_prices(given, expected):
    item = LineItem("x", 1, given)
    assert isinstance(item.unit_price, Decimal)
    assert item.unit_price == expected


@pytest.mark.parametrize(
    "bad",
    [
        1.5,
        2.0,
        True,
        None,
        [1],
        "-0.01",
        -1,
        Decimal("-5"),
        "1.005",
        Decimal("0.001"),
        "abc",
        "",
        "1,50",
        "NaN",
        "Infinity",
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_unit_prices(bad):
    with pytest.raises(ValueError):
        LineItem("x", 1, bad)


def test_line_total_is_exact():
    assert line_total(LineItem("x", 3, "0.10")) == Decimal("0.30")
    assert line_total(LineItem("x", 7, "19.99")) == Decimal("139.93")
    assert line_total(LineItem("x", 1, "0")) == Decimal("0")
    assert line_total(LineItem("x", 1000, "0.01")) == Decimal("10.00")


def test_free_items_are_allowed_in_an_invoice():
    items = [LineItem("gift", 1, "0"), LineItem("pen", 2, "1.25")]
    totals = compute_totals(items, {"standard": "10"})
    assert totals.subtotal == Decimal("2.50")
    assert totals.tax == Decimal("0.25")
    assert totals.total == Decimal("2.75")
