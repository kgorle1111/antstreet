import pytest
from models import LineItem, compute_totals

ITEM = LineItem("x", 1, "1.00")


def test_empty_invoice_is_rejected():
    with pytest.raises(ValueError):
        compute_totals([], {"standard": "10"})
    with pytest.raises(ValueError):
        compute_totals(iter([]), {"standard": "10"})


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError):
        compute_totals([ITEM, LineItem("y", 1, "1.00", "food")], {"standard": "10"})
    with pytest.raises(ValueError):
        compute_totals([ITEM], {})


def test_category_lookup_is_exact():
    with pytest.raises(ValueError):
        compute_totals([LineItem("y", 1, "1.00", "Food")], {"food": "5"})


@pytest.mark.parametrize("rate", [-1, 100.5, "101", 5.0, None, "abc", True, "NaN"])
def test_bad_rate_is_rejected_even_when_unused(rate):
    with pytest.raises(ValueError):
        compute_totals([ITEM], {"standard": "10", "unused": rate})


@pytest.mark.parametrize("discount", [-1, 101, "100.5", 10.0, None, "abc", True, "Infinity"])
def test_bad_discount_is_rejected(discount):
    with pytest.raises(ValueError):
        compute_totals([ITEM], {"standard": "10"}, discount)


def test_boundary_discounts_and_rates_are_accepted():
    assert (
        compute_totals([ITEM], {"standard": 0}, 0).total
        == compute_totals([ITEM], {"standard": "0.0"}, "0.00").total
    )
    assert str(compute_totals([ITEM], {"standard": 100}, 100).total) == "0.00"
    assert str(compute_totals([ITEM], {"standard": 100}, 0).total) == "2.00"
