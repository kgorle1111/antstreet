import dataclasses
from decimal import Decimal

import pytest
from models import LineItem, line_total
from render import render_invoice


def test_defaults_and_fields():
    item = LineItem("Widget", 2, "3.50")
    assert item.description == "Widget"
    assert item.quantity == 2
    assert item.unit_price == Decimal("3.50")
    assert isinstance(item.unit_price, Decimal)
    assert item.category == "standard"
    assert LineItem("Milk", 1, "1.00", "food").category == "food"


def test_line_item_is_frozen():
    item = LineItem("Widget", 2, "3.50")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.quantity = 5
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.description = "other"


@pytest.mark.parametrize("description", ["", None, 5, b"x", "two\nlines"])
def test_bad_descriptions(description):
    with pytest.raises(ValueError):
        LineItem(description, 1, "1.00")


@pytest.mark.parametrize("quantity", [0, -1, 1.0, 2.5, True, "2", None])
def test_bad_quantities(quantity):
    with pytest.raises(ValueError):
        LineItem("Widget", quantity, "1.00")


@pytest.mark.parametrize("category", ["", None, 3])
def test_bad_categories(category):
    with pytest.raises(ValueError):
        LineItem("Widget", 1, "1.00", category)


def test_invalid_item_never_reaches_the_renderer():
    with pytest.raises(ValueError):
        render_invoice("INV-1", "Acme", [LineItem("Widget", 0, "1.00")], {"standard": "0"})


def test_a_valid_item_survives_the_pipeline():
    item = LineItem("Widget", 3, "2.00")
    assert line_total(item) == Decimal("6.00")
    text = render_invoice("INV-1", "Acme", [item], {"standard": "0"})
    assert "Widget | 3 | 2.00 | 6.00" in text.splitlines()
