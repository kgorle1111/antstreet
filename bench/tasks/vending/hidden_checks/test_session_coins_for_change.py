import pytest
from vending import VendingError, VendingMachine


def test_coins_just_inserted_can_be_given_back_as_change():
    m = VendingMachine({"gum": 75}, {"gum": 1})
    for _ in range(4):
        m.insert(25)
    assert m.select("gum") == ("gum", [25])
    assert m.coins() == {5: 0, 10: 0, 25: 3, 100: 0}


def test_empty_float_and_one_big_coin_cannot_make_change():
    m = VendingMachine({"gum": 75}, {"gum": 1})
    m.insert(100)
    with pytest.raises(VendingError) as err:
        m.select("gum")
    assert err.value.reason == "no_change"


def test_session_coins_and_float_are_pooled():
    m = VendingMachine({"gum": 90}, {"gum": 1}, change={10: 1})
    m.insert(100)
    m.insert(25)
    assert m.select("gum") == ("gum", [25, 10])
    assert m.coins() == {5: 0, 10: 0, 25: 0, 100: 1}
