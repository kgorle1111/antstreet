import pytest
from models import LineItem, compute_totals, line_total
from render import render_invoice

RATES = {"standard": "19.6", "food": "5.5", "books": "0"}
ITEMS = [
    LineItem("Desk", 1, "249.99"),
    LineItem("Bread", 12, "1.15", "food"),
    LineItem("Novel", 3, "8.40", "books"),
    LineItem("Chair", 4, "59.95"),
    LineItem("Cheese", 2, "7.77", "food"),
]


@pytest.mark.parametrize("discount", [0, "5", "12.5", 33, 100])
def test_printed_numbers_are_the_computed_totals(discount):
    totals = compute_totals(ITEMS, RATES, discount)
    lines = render_invoice("N-9", "Customer", ITEMS, RATES, discount).splitlines()
    assert f"Subtotal: {totals.subtotal:.2f}" in lines
    assert f"Total: {totals.total:.2f}" == lines[-1]
    if discount != 0:
        assert any(line.endswith(f"%): -{totals.discount:.2f}") for line in lines)
    printed_tax = [line.rsplit(": ", 1)[1] for line in lines if line.startswith("Tax (")]
    assert printed_tax == [f"{t:.2f}" for t in totals.tax_by_category.values()]
    assert len(printed_tax) == 3


def test_item_rows_use_line_total():
    lines = render_invoice("N", "C", ITEMS, RATES).splitlines()
    for item, row in zip(ITEMS, lines[4:9], strict=True):
        assert row == (
            f"{item.description} | {item.quantity} | {item.unit_price:.2f} | {line_total(item):.2f}"
        )


@pytest.mark.parametrize("number", ["", None, 7, "a\nb"])
def test_bad_number_is_rejected(number):
    with pytest.raises(ValueError):
        render_invoice(number, "C", ITEMS, RATES)


@pytest.mark.parametrize("customer", ["", None, 7, "a\nb"])
def test_bad_customer_is_rejected(customer):
    with pytest.raises(ValueError):
        render_invoice("N", customer, ITEMS, RATES)


def test_money_errors_propagate_unchanged():
    with pytest.raises(ValueError):
        render_invoice("N", "C", [], RATES)
    with pytest.raises(ValueError):
        render_invoice("N", "C", ITEMS, {"standard": "19.6"})
    with pytest.raises(ValueError):
        render_invoice("N", "C", ITEMS, RATES, 101)
    with pytest.raises(ValueError):
        render_invoice("N", "C", ITEMS, {**RATES, "standard": 120})


def test_inputs_are_not_modified():
    items = list(ITEMS)
    rates = dict(RATES)
    render_invoice("N", "C", items, rates, 10)
    assert items == ITEMS and rates == RATES
