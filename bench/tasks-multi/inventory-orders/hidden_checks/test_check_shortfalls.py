import pytest
from items import Inventory
from orders import OrderBook


@pytest.fixture
def shop():
    inv = Inventory()
    inv.add_stock("apple", 10)
    inv.add_stock("bread", 4)
    inv.add_stock("cheese", 2)
    return inv, OrderBook(inv)


def test_nothing_short_gives_an_empty_dict(shop):
    _, book = shop
    assert book.check({"apple": 10, "bread": 1}) == {}


def test_shortfall_is_requested_minus_available(shop):
    inv, book = shop
    assert book.check({"apple": 12}) == {"apple": 2}
    inv.reserve("apple", 7)
    assert book.check({"apple": 12}) == {"apple": 9}
    assert book.check({"apple": 3}) == {}
    assert book.check({"apple": 4}) == {"apple": 1}


def test_keys_are_in_ascending_order(shop):
    _, book = shop
    result = book.check({"cheese": 5, "bread": 9, "apple": 11})
    assert list(result) == ["apple", "bread", "cheese"]
    assert result == {"apple": 1, "bread": 5, "cheese": 3}


def test_only_the_short_skus_are_listed(shop):
    _, book = shop
    assert book.check({"apple": 1, "bread": 5, "cheese": 2}) == {"bread": 1}


def test_check_merges_duplicates_and_accepts_pairs(shop):
    _, book = shop
    assert book.check([("cheese", 1), ("cheese", 2)]) == {"cheese": 1}
    assert book.check(iter([("bread", 3), ("bread", 3)])) == {"bread": 2}


def test_check_changes_nothing(shop):
    inv, book = shop
    book.check({"apple": 99, "bread": 1})
    book.check({"apple": 1})
    assert inv.reserved("apple") == 0 and inv.reserved("bread") == 0
    assert book.open_orders() == []
    assert book.place({"apple": 1}) == 1


def test_check_unknown_sku_is_a_key_error_for_the_first_unknown(shop):
    _, book = shop
    with pytest.raises(KeyError) as info:
        book.check({"zebra": 1, "yak": 1, "apple": 99})
    assert "yak" in str(info.value)


@pytest.mark.parametrize(
    "lines",
    [
        {},
        [],
        iter([]),
        {"": 1},
        {None: 1},
        {5: 1},
        {"apple": 0},
        {"apple": -1},
        {"apple": 1.0},
        {"apple": True},
        {"apple": "1"},
        {"apple": None},
        [("apple", 1), ("", 1)],
        [("apple", 0), ("bread", 1)],
    ],
)
def test_invalid_lines_are_value_errors(shop, lines):
    inv, book = shop
    with pytest.raises(ValueError):
        book.check(lines)
    with pytest.raises(ValueError):
        book.place(lines)
    assert inv.reserved("apple") == 0
    assert book.open_orders() == []


def test_value_error_wins_over_unknown_sku(shop):
    _, book = shop
    with pytest.raises(ValueError):
        book.place([("zebra", 1), ("apple", 0)])
