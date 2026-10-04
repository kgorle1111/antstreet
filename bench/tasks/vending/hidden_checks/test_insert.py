import pytest
from vending import VendingError, VendingMachine


def machine():
    return VendingMachine({"cola": 100}, {"cola": 5})


def test_credit_starts_at_zero_and_sums_coins():
    m = machine()
    assert m.credit == 0
    for coin in (5, 10, 25, 100):
        m.insert(coin)
    assert m.credit == 140


@pytest.mark.parametrize("coin", [0, 1, 2, 20, 50, 200, -5])
def test_unaccepted_coin_raises_and_changes_nothing(coin):
    m = machine()
    m.insert(25)
    with pytest.raises(ValueError):
        m.insert(coin)
    assert m.credit == 25


def test_credit_may_reach_exactly_the_limit():
    m = machine()
    for _ in range(4):
        m.insert(100)
    for _ in range(4):
        m.insert(25)
    assert m.credit == 500


def test_a_coin_over_the_limit_is_refused_and_not_taken():
    m = machine()
    for _ in range(5):
        m.insert(100)
    with pytest.raises(VendingError) as err:
        m.insert(5)
    assert err.value.reason == "credit_limit"
    assert str(err.value) == "credit_limit"
    assert m.credit == 500
    assert m.refund() == [100, 100, 100, 100, 100]


def test_limit_applies_to_the_coin_that_would_cross_it():
    m = machine()
    for _ in range(4):
        m.insert(100)
    m.insert(25)
    m.insert(25)
    with pytest.raises(VendingError):
        m.insert(100)
    assert m.credit == 450
    m.insert(25)
    m.insert(25)
    assert m.credit == 500
    with pytest.raises(VendingError):
        m.insert(5)
    assert m.credit == 500
