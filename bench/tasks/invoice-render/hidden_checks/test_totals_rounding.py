from decimal import Decimal

from models import LineItem, compute_totals


def D(text):
    return Decimal(text)


def test_tax_is_rounded_once_per_category_not_per_item():
    items = [LineItem(f"i{n}", 1, "0.35") for n in range(3)]
    totals = compute_totals(items, {"standard": "10"})
    # 1.05 * 10% = 0.105 -> 0.11; rounding each 0.035 first would give 0.12
    assert totals.tax == D("0.11")
    assert totals.total == D("1.16")


def test_tax_rounding_is_half_up_not_half_even():
    totals = compute_totals([LineItem("x", 1, "0.35")], {"standard": "10"})
    assert totals.tax == D("0.04")  # 0.035
    totals = compute_totals([LineItem("x", 3, "0.35")], {"standard": "10"})
    assert totals.tax == D("0.11")  # 0.105; half-even would give 0.10
    totals = compute_totals([LineItem("x", 1, "0.25")], {"standard": "10"})
    assert totals.tax == D("0.03")  # 0.025; half-even would give 0.02


def test_discount_rounding_is_half_up_per_item():
    totals = compute_totals([LineItem("x", 1, "0.05")], {"standard": "0"}, 10)
    assert totals.net == D("0.05")  # 0.045 -> 0.05; half-even would give 0.04
    assert totals.discount == D("0.00")


def test_discount_is_applied_to_each_item_not_to_the_total():
    items = [LineItem(f"i{n}", 1, "0.05") for n in range(3)]
    totals = compute_totals(items, {"standard": "0"}, 10)
    assert totals.subtotal == D("0.15")
    assert totals.net == D("0.15")  # 3 x 0.05; discounting 0.15 once would give 0.14
    assert totals.discount == D("0.00")


def test_discount_comes_before_tax():
    totals = compute_totals([LineItem("x", 1, "100.00")], {"standard": "10"}, 50)
    assert totals.net == D("50.00")
    assert totals.discount == D("50.00")
    assert totals.tax == D("5.00")
    assert totals.total == D("55.00")


def test_discount_percent_may_be_fractional_and_of_any_accepted_type():
    for given in ("12.5", Decimal("12.5")):
        totals = compute_totals([LineItem("x", 1, "10.00")], {"standard": "0"}, given)
        assert totals.net == D("8.75")
        assert totals.discount == D("1.25")
    totals = compute_totals([LineItem("x", 1, "10.00")], {"standard": "0"}, 25)
    assert totals.net == D("7.50")


def test_rates_may_be_fractional_and_of_any_accepted_type():
    for rate in ("7.25", Decimal("7.25")):
        totals = compute_totals([LineItem("x", 4, "25.00")], {"standard": rate})
        assert totals.tax == D("7.25")
        assert totals.total == D("107.25")


def test_large_invoice_stays_exact():
    items = [LineItem(f"i{n}", 3, "0.10") for n in range(1000)]
    totals = compute_totals(items, {"standard": "20"})
    assert totals.subtotal == D("300.00")
    assert totals.tax == D("60.00")
    assert totals.total == D("360.00")


def test_discount_and_tax_across_categories_use_the_discounted_net_of_each():
    items = [
        LineItem("a", 1, "10.01", "x"),
        LineItem("b", 1, "10.01", "y"),
        LineItem("c", 1, "10.01", "x"),
    ]
    totals = compute_totals(items, {"x": "15", "y": "7"}, 33)
    # each net: 10.01 * 0.67 = 6.7067 -> 6.71
    assert totals.net == D("20.13")
    assert totals.discount == D("9.90")
    assert totals.tax_by_category == {"x": D("2.01"), "y": D("0.47")}
    assert totals.total == D("22.61")
