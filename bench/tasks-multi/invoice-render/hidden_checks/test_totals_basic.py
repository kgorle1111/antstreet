from decimal import Decimal

from models import LineItem, Totals, compute_totals


def D(text):
    return Decimal(text)


def test_single_item_no_discount():
    totals = compute_totals([LineItem("Widget", 2, "3.50")], {"standard": "10"})
    assert isinstance(totals, Totals)
    assert totals.subtotal == D("7.00")
    assert totals.discount == D("0.00")
    assert totals.net == D("7.00")
    assert totals.tax_by_category == {"standard": D("0.70")}
    assert totals.tax == D("0.70")
    assert totals.total == D("7.70")


def test_example_from_the_idea():
    totals = compute_totals([LineItem("Widget", 2, "3.50")], {"standard": "8.50"}, 10)
    assert totals.subtotal == D("7.00")
    assert totals.discount == D("0.70")
    assert totals.net == D("6.30")
    assert totals.tax == D("0.54")
    assert totals.total == D("6.84")


def test_two_categories_keep_first_appearance_order():
    items = [
        LineItem("milk", 2, "1.20", "food"),
        LineItem("lamp", 1, "40.00"),
        LineItem("bread", 1, "2.50", "food"),
    ]
    totals = compute_totals(items, {"standard": "20", "food": "5", "unused": "50"})
    assert list(totals.tax_by_category) == ["food", "standard"]
    assert totals.tax_by_category == {"food": D("0.25"), "standard": D("8.00")}
    assert totals.subtotal == D("44.90")
    assert totals.tax == D("8.25")
    assert totals.total == D("53.15")


def test_zero_rate_category_is_listed_with_zero_tax():
    items = [LineItem("book", 3, "9.99", "books"), LineItem("pen", 1, "1.00")]
    totals = compute_totals(items, {"books": "0", "standard": "10"})
    assert totals.tax_by_category == {"books": D("0.00"), "standard": D("0.10")}
    assert totals.subtotal == D("30.97")
    assert totals.total == D("31.07")


def test_amounts_have_two_decimal_places():
    totals = compute_totals([LineItem("x", 1, "5")], {"standard": "0"})
    for amount in (totals.subtotal, totals.discount, totals.net, totals.tax, totals.total):
        assert isinstance(amount, Decimal)
        assert amount.as_tuple().exponent == -2
    assert all(v.as_tuple().exponent == -2 for v in totals.tax_by_category.values())


def test_full_discount():
    totals = compute_totals([LineItem("x", 2, "10.00")], {"standard": "20"}, 100)
    assert totals.subtotal == D("20.00")
    assert totals.discount == D("20.00")
    assert totals.net == D("0.00")
    assert totals.tax == D("0.00")
    assert totals.total == D("0.00")


def test_arguments_are_not_modified_and_any_iterable_works():
    items = (LineItem("a", 1, "1.00"), LineItem("b", 1, "2.00", "food"))
    rates = {"standard": "10", "food": 5}
    snapshot = dict(rates)
    totals = compute_totals(items, rates, "5")
    assert rates == snapshot
    assert totals.subtotal == D("3.00")
    assert compute_totals(iter(items), rates, "5") == totals


def test_totals_is_a_value():
    one = compute_totals([LineItem("a", 1, "1.00")], {"standard": "10"})
    two = compute_totals([LineItem("a", 1, "1.00")], {"standard": "10"})
    assert one == two
