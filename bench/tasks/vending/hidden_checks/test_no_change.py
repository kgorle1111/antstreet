import pytest
from vending import VendingError, VendingMachine


def test_no_change_fails_and_keeps_everything():
    m = VendingMachine({"chips": 65}, {"chips": 2})
    m.insert(100)
    with pytest.raises(VendingError) as err:
        m.select("chips")
    assert err.value.reason == "no_change"
    assert m.credit == 100
    assert m.remaining("chips") == 2
    assert m.coins() == {5: 0, 10: 0, 25: 0, 100: 0}
    assert m.refund() == [100]


def test_change_is_greedy_not_optimal():
    m = VendingMachine({"chips": 70}, {"chips": 1}, change={25: 1, 10: 3})
    m.insert(100)
    with pytest.raises(VendingError) as err:
        m.select("chips")
    assert err.value.reason == "no_change"
    assert m.credit == 100
    assert m.coins() == {5: 0, 10: 3, 25: 1, 100: 0}


def test_after_a_failed_sale_more_coins_can_fix_it():
    m = VendingMachine({"chips": 65}, {"chips": 1})
    m.insert(100)
    with pytest.raises(VendingError):
        m.select("chips")
    m.insert(25)
    m.insert(10)
    m.insert(5)
    m.insert(25)
    # credit 165, change 100 comes back from the pooled coins
    assert m.select("chips") == ("chips", [100])


def test_a_failed_sale_does_not_use_up_stock():
    m = VendingMachine({"chips": 65}, {"chips": 1})
    m.insert(100)
    with pytest.raises(VendingError):
        m.select("chips")
    assert m.remaining("chips") == 1
