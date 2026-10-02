import pytest
from items import Inventory
from orders import OrderBook, OrderError


@pytest.fixture
def shop():
    inv = Inventory()
    inv.add_stock("apple", 10)
    inv.add_stock("bread", 4)
    return inv, OrderBook(inv)


def test_ship_moves_stock_out_of_the_building(shop):
    inv, book = shop
    order = book.place({"apple": 3, "bread": 1})
    book.ship(order)
    assert book.status(order) == "shipped"
    assert (inv.on_hand("apple"), inv.reserved("apple"), inv.available("apple")) == (7, 0, 7)
    assert (inv.on_hand("bread"), inv.reserved("bread"), inv.available("bread")) == (3, 0, 3)
    assert book.open_orders() == []


def test_cancel_returns_the_reservation(shop):
    inv, book = shop
    order = book.place({"apple": 3, "bread": 1})
    book.cancel(order)
    assert book.status(order) == "cancelled"
    assert (inv.on_hand("apple"), inv.reserved("apple"), inv.available("apple")) == (10, 0, 10)
    assert inv.available("bread") == 4
    assert book.open_orders() == []


def test_lines_stay_readable_after_ship_and_cancel(shop):
    _, book = shop
    one, two = book.place({"apple": 1}), book.place({"bread": 2})
    book.ship(one)
    book.cancel(two)
    assert book.lines(one) == [("apple", 1)]
    assert book.lines(two) == [("bread", 2)]


@pytest.mark.parametrize("first", ["ship", "cancel"])
@pytest.mark.parametrize("second", ["ship", "cancel"])
def test_a_finished_order_cannot_be_ship_or_cancelled_again(shop, first, second):
    inv, book = shop
    order = book.place({"apple": 4})
    getattr(book, first)(order)
    status = book.status(order)
    state = (inv.on_hand("apple"), inv.reserved("apple"))
    with pytest.raises(OrderError):
        getattr(book, second)(order)
    assert book.status(order) == status
    assert (inv.on_hand("apple"), inv.reserved("apple")) == state


def test_order_error_is_an_exception_of_its_own():
    assert issubclass(OrderError, Exception)
    assert not issubclass(OrderError, (KeyError, ValueError))


def test_cancel_frees_stock_for_the_next_order(shop):
    inv, book = shop
    first = book.place({"bread": 4})
    assert book.check({"bread": 1}) == {"bread": 1}
    book.cancel(first)
    second = book.place({"bread": 4})
    assert second == 2
    assert book.open_orders() == [2]


def test_shipped_stock_is_gone_for_good(shop):
    inv, book = shop
    order = book.place({"bread": 4})
    book.ship(order)
    assert book.check({"bread": 1}) == {"bread": 1}
    inv.add_stock("bread", 1)
    assert book.place({"bread": 1}) == 2


def test_ship_and_cancel_only_touch_their_own_order(shop):
    inv, book = shop
    a, b, c = (book.place({"apple": 2}) for _ in range(3))
    book.cancel(b)
    book.ship(a)
    assert book.open_orders() == [c]
    assert (inv.on_hand("apple"), inv.reserved("apple")) == (8, 2)
    book.ship(c)
    assert (inv.on_hand("apple"), inv.reserved("apple")) == (6, 0)


def test_whole_lifecycle_numbers_add_up(shop):
    inv, book = shop
    ids = [book.place({"apple": 2, "bread": 1}) for _ in range(4)]
    assert inv.available("bread") == 0
    book.ship(ids[0])
    book.cancel(ids[1])
    book.ship(ids[2])
    assert (inv.on_hand("apple"), inv.reserved("apple"), inv.available("apple")) == (6, 2, 4)
    assert (inv.on_hand("bread"), inv.reserved("bread"), inv.available("bread")) == (2, 1, 1)
    assert [book.status(i) for i in ids] == ["shipped", "cancelled", "shipped", "reserved"]
