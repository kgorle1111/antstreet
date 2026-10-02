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


def test_place_reserves_every_line_and_returns_ids_from_one(shop):
    inv, book = shop
    assert book.place({"apple": 3, "bread": 1}) == 1
    assert book.place({"cheese": 2}) == 2
    assert inv.reserved("apple") == 3 and inv.available("apple") == 7
    assert inv.reserved("bread") == 1
    assert inv.reserved("cheese") == 2 and inv.available("cheese") == 0
    assert inv.on_hand("apple") == 10


def test_lines_as_a_list_of_pairs_and_any_iterable(shop):
    inv, book = shop
    assert book.place([("bread", 2), ("apple", 1)]) == 1
    assert book.place(iter([("apple", 2)])) == 2
    assert book.place(pair for pair in [("cheese", 1)]) == 3
    assert inv.reserved("apple") == 3 and inv.reserved("bread") == 2


def test_duplicate_skus_are_merged_by_adding(shop):
    inv, book = shop
    order = book.place([("apple", 2), ("bread", 1), ("apple", 3)])
    assert book.lines(order) == [("apple", 5), ("bread", 1)]
    assert inv.reserved("apple") == 5


def test_merged_duplicates_are_what_is_checked_against_stock(shop):
    inv, book = shop
    with pytest.raises(InsufficientStock) as info:
        book.place([("cheese", 1), ("cheese", 2)])
    assert (info.value.sku, info.value.requested, info.value.available) == ("cheese", 3, 2)
    assert inv.reserved("cheese") == 0


def test_lines_come_back_in_sku_order_as_a_new_list(shop):
    _, book = shop
    order = book.place({"cheese": 1, "apple": 2, "bread": 1})
    lines = book.lines(order)
    assert lines == [("apple", 2), ("bread", 1), ("cheese", 1)]
    lines.clear()
    assert book.lines(order) == [("apple", 2), ("bread", 1), ("cheese", 1)]


def test_order_can_take_everything_that_is_available(shop):
    inv, book = shop
    book.place({"apple": 10, "bread": 4, "cheese": 2})
    assert [inv.available(s) for s in ("apple", "bread", "cheese")] == [0, 0, 0]


def test_second_order_sees_what_the_first_reserved(shop):
    inv, book = shop
    book.place({"bread": 3})
    assert book.check({"bread": 2}) == {"bread": 1}
    with pytest.raises(InsufficientStock) as info:
        book.place({"bread": 2})
    assert info.value.available == 1


def test_new_status_and_open_orders(shop):
    _, book = shop
    first = book.place({"apple": 1})
    second = book.place({"apple": 1})
    assert book.status(first) == book.status(second) == "reserved"
    assert book.open_orders() == [first, second]
    listing = book.open_orders()
    listing.clear()
    assert book.open_orders() == [first, second]


def test_unknown_order_id(shop):
    _, book = shop
    for call in (book.status, book.lines, book.ship, book.cancel):
        with pytest.raises(KeyError):
            call(1)
    book.place({"apple": 1})
    with pytest.raises(KeyError):
        book.status(2)
    with pytest.raises(KeyError):
        book.status(0)
