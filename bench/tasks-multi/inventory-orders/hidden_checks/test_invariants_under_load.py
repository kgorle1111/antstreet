import contextlib

from items import InsufficientStock, Inventory
from orders import OrderBook

SKUS = ["a", "b", "c", "d"]


def lcg(seed):
    state = seed
    while True:
        state = (state * 1103515245 + 12345) % (2**31)
        yield state >> 8


def test_reserved_always_equals_what_open_orders_hold():
    inv = Inventory()
    for sku in SKUS:
        inv.add_stock(sku, 40)
    book = OrderBook(inv)
    rnd = lcg(7)
    shipped = dict.fromkeys(SKUS, 0)
    for _ in range(300):
        action = next(rnd) % 4
        if action < 2:
            lines = {SKUS[next(rnd) % 4]: 1 + next(rnd) % 6 for _ in range(1 + next(rnd) % 3)}
            with contextlib.suppress(InsufficientStock):
                book.place(lines)
        elif action == 2 and book.open_orders():
            order = book.open_orders()[next(rnd) % len(book.open_orders())]
            for sku, qty in book.lines(order):
                shipped[sku] += qty
            book.ship(order)
        elif book.open_orders():
            book.cancel(book.open_orders()[next(rnd) % len(book.open_orders())])
        held = dict.fromkeys(SKUS, 0)
        for order in book.open_orders():
            for sku, qty in book.lines(order):
                held[sku] += qty
        for sku in SKUS:
            assert inv.reserved(sku) == held[sku]
            assert inv.available(sku) == inv.on_hand(sku) - inv.reserved(sku) >= 0
            assert inv.on_hand(sku) == 40 - shipped[sku]


def test_ids_are_dense_and_statuses_are_consistent():
    inv = Inventory()
    inv.add_stock("a", 5)
    book = OrderBook(inv)
    ids = []
    for qty in (2, 2, 2, 1, 1):
        try:
            ids.append(book.place({"a": qty}))
        except InsufficientStock:
            ids.append(None)
    assert ids == [1, 2, None, 3, None]
    assert book.open_orders() == [1, 2, 3]
    book.cancel(2)
    assert book.place({"a": 2}) == 4
    assert [book.status(i) for i in (1, 2, 3, 4)] == [
        "reserved",
        "cancelled",
        "reserved",
        "reserved",
    ]


def test_competing_orders_for_the_last_units():
    inv = Inventory()
    inv.add_stock("a", 3)
    book = OrderBook(inv)
    first = book.place({"a": 2})
    try:
        book.place({"a": 2})
        raise AssertionError("second order should not fit")
    except InsufficientStock as error:
        assert error.available == 1
    second = book.place({"a": 1})
    book.cancel(first)
    third = book.place({"a": 2})
    assert (first, second, third) == (1, 2, 3)
    assert inv.available("a") == 0
    book.ship(second)
    book.ship(third)
    assert (inv.on_hand("a"), inv.reserved("a")) == (0, 0)
