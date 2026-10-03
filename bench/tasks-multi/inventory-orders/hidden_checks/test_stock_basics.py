import pytest
from items import Inventory
from orders import OrderBook


def test_empty_inventory():
    inv = Inventory()
    assert inv.skus() == []
    assert inv.on_hand("x") == inv.reserved("x") == inv.available("x") == 0
    assert "x" not in inv
    assert inv.skus() == []


def test_add_stock_creates_and_accumulates():
    inv = Inventory()
    inv.add_stock("bolt", 10)
    inv.add_stock("nut", 5)
    inv.add_stock("bolt", 7)
    assert inv.on_hand("bolt") == 17
    assert inv.on_hand("nut") == 5
    assert inv.reserved("bolt") == 0
    assert inv.available("bolt") == 17
    assert "bolt" in inv and "nut" in inv and "washer" not in inv


def test_skus_are_sorted_and_a_new_list():
    inv = Inventory()
    for sku in ("pear", "apple", "fig", "Zucchini"):
        inv.add_stock(sku, 1)
    names = inv.skus()
    assert names == ["Zucchini", "apple", "fig", "pear"]
    names.clear()
    assert inv.skus() == ["Zucchini", "apple", "fig", "pear"]


def test_reads_of_unknown_skus_do_not_create_them():
    inv = Inventory()
    inv.available("ghost")
    inv.on_hand("ghost")
    inv.reserved("ghost")
    assert "ghost" not in inv
    assert inv.skus() == []


@pytest.mark.parametrize("sku", ["", None, 5, b"x", ("a",)])
def test_bad_sku_everywhere(sku):
    inv = Inventory()
    inv.add_stock("real", 1)
    for call in (inv.add_stock, inv.reserve, inv.release, inv.ship):
        with pytest.raises(ValueError):
            call(sku, 1)


@pytest.mark.parametrize("qty", [0, -1, 1.0, 2.5, True, False, "1", None])
def test_bad_quantity_everywhere(qty):
    inv = Inventory()
    inv.add_stock("real", 5)
    for call in (inv.add_stock, inv.reserve, inv.release, inv.ship):
        with pytest.raises(ValueError):
            call("real", qty)
    assert inv.on_hand("real") == 5 and inv.reserved("real") == 0


def test_validation_comes_before_the_unknown_sku_check():
    inv = Inventory()
    with pytest.raises(ValueError):
        inv.reserve("unknown", 0)
    with pytest.raises(ValueError):
        inv.release("unknown", -1)
    with pytest.raises(ValueError):
        inv.ship("unknown", True)


def test_two_inventories_are_independent():
    one, two = Inventory(), Inventory()
    one.add_stock("a", 3)
    assert two.on_hand("a") == 0
    book = OrderBook(two)
    with pytest.raises(KeyError):
        book.place({"a": 1})
