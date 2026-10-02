from decimal import Decimal

import pytest
from models import LineItem, compute_totals, parse_percent


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("8.5", Decimal("8.5")),
        ("8.50", Decimal("8.50")),
        (10, Decimal("10")),
        (Decimal("0.25"), Decimal("0.25")),
        (0, Decimal("0")),
        ("0", Decimal("0")),
        (100, Decimal("100")),
        ("100.00", Decimal("100")),
        ("12.3456", Decimal("12.3456")),
    ],
)
def test_valid_percentages(given, expected):
    result = parse_percent(given)
    assert isinstance(result, Decimal)
    assert result == expected


@pytest.mark.parametrize(
    "bad",
    [
        -1,
        "-0.1",
        101,
        "100.01",
        Decimal("1000"),
        8.5,
        0.0,
        True,
        None,
        "ten",
        "",
        "NaN",
        "Infinity",
    ],
)
def test_invalid_percentages(bad):
    with pytest.raises(ValueError):
        parse_percent(bad)


def test_compute_totals_validates_rates_and_discount_with_parse_percent():
    items = [LineItem("x", 1, "1.00")]
    for bad in [101, -1, 5.5, "x", None]:
        with pytest.raises(ValueError):
            compute_totals(items, {"standard": bad})
        with pytest.raises(ValueError):
            compute_totals(items, {"standard": "0"}, bad)
