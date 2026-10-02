import pytest
from items import Inventory


def test_ship_removes_units_from_stock_and_reservation():
    inv = Inventory()
    inv.add_stock("a", 10)
    inv.reserve("a", 6)
    inv.ship("a", 4)
    assert inv.on_hand("a") == 6
    assert inv.reserved("a") == 2
    assert inv.available("a") == 4


def test_ship_everything_reserved():
    inv = Inventory()
    inv.add_stock("a", 5)
    inv.reserve("a", 5)
    inv.ship("a", 5)
    assert (inv.on_hand("a"), inv.reserved("a"), inv.available("a")) == (0, 0, 0)
    assert "a" in inv
    assert inv.skus() == ["a"]


def test_ship_more_than_reserved_is_a_value_error_and_changes_nothing():
    inv = Inventory()
    inv.add_stock("a", 10)
    inv.reserve("a", 3)
    with pytest.raises(ValueError):
        inv.ship("a", 4)
    assert (inv.on_hand("a"), inv.reserved("a")) == (10, 3)
    with pytest.raises(ValueError):
        inv.ship("a", 11)


def test_ship_unreserved_stock_is_refused():
    inv = Inventory()
    inv.add_stock("a", 10)
    with pytest.raises(ValueError):
        inv.ship("a", 1)
    assert inv.on_hand("a") == 10


def test_ship_unknown_sku_is_a_key_error():
    with pytest.raises(KeyError):
        Inventory().ship("nope", 1)


def test_shipping_then_restocking():
    inv = Inventory()
    inv.add_stock("a", 4)
    inv.reserve("a", 4)
    inv.ship("a", 4)
    inv.add_stock("a", 6)
    assert (inv.on_hand("a"), inv.reserved("a"), inv.available("a")) == (6, 0, 6)


def test_partial_ship_then_release_the_rest():
    inv = Inventory()
    inv.add_stock("a", 10)
    inv.reserve("a", 5)
    inv.ship("a", 2)
    inv.release("a", 3)
    assert (inv.on_hand("a"), inv.reserved("a"), inv.available("a")) == (8, 0, 8)
