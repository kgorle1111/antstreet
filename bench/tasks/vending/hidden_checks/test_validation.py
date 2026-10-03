import pytest
from vending import VendingMachine


@pytest.mark.parametrize("price", [0, -5, 1.5, "10", None])
def test_bad_price_raises(price):
    with pytest.raises(ValueError):
        VendingMachine({"a": price}, {"a": 1})


@pytest.mark.parametrize("count", [-1, 2.5, "3"])
def test_bad_stock_count_raises(count):
    with pytest.raises(ValueError):
        VendingMachine({"a": 10}, {"a": count})


def test_stock_for_an_unknown_item_raises():
    with pytest.raises(ValueError):
        VendingMachine({"a": 10}, {"a": 1, "ghost": 1})


@pytest.mark.parametrize("coin", [1, 2, 50, 200, 0])
def test_float_with_an_unknown_coin_raises(coin):
    with pytest.raises(ValueError):
        VendingMachine({"a": 10}, {"a": 1}, change={coin: 1})


def test_negative_float_count_raises():
    with pytest.raises(ValueError):
        VendingMachine({"a": 10}, {"a": 1}, change={25: -1})


def test_constructor_copies_its_arguments():
    prices, stock, change = {"a": 10}, {"a": 1}, {5: 1}
    m = VendingMachine(prices, stock, change)
    prices["a"] = 999
    stock["a"] = 999
    change[5] = 999
    assert m.remaining("a") == 1
    assert m.coins()[5] == 1
    m.insert(10)
    assert m.select("a") == ("a", [])


def test_valid_machine_with_no_items_or_float():
    m = VendingMachine({}, {})
    assert m.credit == 0
    assert m.coins() == {5: 0, 10: 0, 25: 0, 100: 0}
