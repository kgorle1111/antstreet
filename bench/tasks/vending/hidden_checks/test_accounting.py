import pytest
from vending import VendingMachine


def test_remaining_tracks_every_sale():
    m = VendingMachine({"a": 10, "b": 20}, {"a": 3, "b": 1})
    for _ in range(3):
        m.insert(10)
        m.select("a")
    assert m.remaining("a") == 0
    assert m.remaining("b") == 1


def test_item_without_a_stock_entry_has_none():
    m = VendingMachine({"a": 10, "b": 20}, {"a": 3})
    assert m.remaining("b") == 0


def test_remaining_of_an_unknown_item_raises_key_error():
    m = VendingMachine({"a": 10}, {"a": 1})
    with pytest.raises(KeyError):
        m.remaining("zzz")


def test_coins_has_an_entry_for_every_denomination_and_is_a_copy():
    m = VendingMachine({"a": 10}, {"a": 1}, change={25: 2})
    snapshot = m.coins()
    assert snapshot == {5: 0, 10: 0, 25: 2, 100: 0}
    snapshot[25] = 99
    assert m.coins()[25] == 2


def test_float_pays_out_across_several_sales():
    m = VendingMachine({"a": 90}, {"a": 3}, change={10: 3})
    for paid_so_far in range(3):
        m.insert(100)
        assert m.select("a") == ("a", [10])
        assert m.coins() == {5: 0, 10: 2 - paid_so_far, 25: 0, 100: paid_so_far + 1}
    assert m.remaining("a") == 0
