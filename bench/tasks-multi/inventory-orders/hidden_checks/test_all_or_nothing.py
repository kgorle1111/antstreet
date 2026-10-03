import pytest
from items import InsufficientStock, Inventory
from orders import OrderBook


@pytest.fixture
def shop():
    inv = Inventory()
    inv.add_stock("apple", 10)
    inv.add_stock("bread", 4)
    inv.add_stock("cheese", 2)
    return inv, OrderBook(inv)


def snapshot(inv):
    return {s: (inv.on_hand(s), inv.reserved(s), inv.available(s)) for s in inv.skus()}


def test_a_short_line_rejects_the_whole_order_and_reserves_nothing(shop):
    inv, book = shop
    before = snapshot(inv)
    with pytest.raises(InsufficientStock) as info:
        book.place({"apple": 5, "bread": 1, "cheese": 3})
    assert (info.value.sku, info.value.requested, info.value.available) == ("cheese", 3, 2)
    assert snapshot(inv) == before
    assert book.open_orders() == []


def test_the_failing_line_may_come_first_in_sku_order(shop):
    inv, book = shop
    before = snapshot(inv)
    with pytest.raises(InsufficientStock) as info:
        book.place({"apple": 11, "bread": 1})
    assert info.value.sku == "apple"
    assert snapshot(inv) == before


def test_with_several_short_lines_the_first_in_sku_order_is_reported(shop):
    _, book = shop
    with pytest.raises(InsufficientStock) as info:
        book.place({"cheese": 9, "bread": 9, "apple": 1})
    assert (info.value.sku, info.value.requested, info.value.available) == ("bread", 9, 4)


def test_unknown_sku_is_a_key_error_and_reserves_nothing(shop):
    inv, book = shop
    before = snapshot(inv)
    with pytest.raises(KeyError) as info:
        book.place({"apple": 1, "zebra": 1})
    assert "zebra" in str(info.value)
    assert snapshot(inv) == before
    assert "zebra" not in inv


def test_unknown_sku_is_reported_before_a_shortage(shop):
    _, book = shop
    with pytest.raises(KeyError):
        book.place({"apple": 99, "zebra": 1})
    with pytest.raises(KeyError) as info:
        book.place({"yak": 1, "zebra": 1, "apple": 99})
    assert "yak" in str(info.value)


def test_a_failed_placement_does_not_use_up_an_order_id(shop):
    _, book = shop
    assert book.place({"apple": 1}) == 1
    with pytest.raises(InsufficientStock):
        book.place({"bread": 5})
    with pytest.raises(KeyError):
        book.place({"nope": 1})
    with pytest.raises(ValueError):
        book.place({"apple": 0})
    assert book.place({"apple": 1}) == 2
    assert book.open_orders() == [1, 2]


def test_a_rejected_order_leaves_earlier_orders_alone(shop):
    inv, book = shop
    first = book.place({"apple": 4, "bread": 2})
    with pytest.raises(InsufficientStock):
        book.place({"apple": 6, "bread": 3})
    assert book.status(first) == "reserved"
    assert inv.reserved("apple") == 4 and inv.reserved("bread") == 2


def test_the_same_order_succeeds_once_stock_arrives(shop):
    inv, book = shop
    with pytest.raises(InsufficientStock):
        book.place({"cheese": 5, "apple": 1})
    inv.add_stock("cheese", 3)
    assert book.place({"cheese": 5, "apple": 1}) == 1
    assert inv.available("cheese") == 0


def test_check_agrees_with_place(shop):
    inv, book = shop
    lines = {"apple": 11, "bread": 4, "cheese": 3}
    assert book.check(lines) == {"apple": 1, "cheese": 1}
    with pytest.raises(InsufficientStock):
        book.place(lines)
    assert book.check({"apple": 10}) == {}
    assert book.place({"apple": 10}) == 1
