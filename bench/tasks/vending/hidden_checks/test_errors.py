import pytest
from vending import VendingError, VendingMachine


def machine():
    return VendingMachine({"cola": 100, "gum": 35, "tea": 50}, {"cola": 1, "gum": 0})


def reason(m, item):
    with pytest.raises(VendingError) as err:
        m.select(item)
    return err.value.reason


def test_unknown_item():
    m = machine()
    m.insert(100)
    assert reason(m, "water") == "unknown_item"
    assert m.credit == 100


def test_sold_out_from_the_start_and_after_the_last_unit():
    m = machine()
    m.insert(100)
    assert reason(m, "gum") == "sold_out"
    assert reason(m, "tea") == "sold_out"
    m.select("cola")
    m.insert(100)
    assert reason(m, "cola") == "sold_out"
    assert m.credit == 100


def test_insufficient_credit():
    m = VendingMachine({"cola": 100}, {"cola": 1})
    m.insert(25)
    assert reason(m, "cola") == "insufficient_credit"
    assert m.credit == 25
    assert m.remaining("cola") == 1


def test_sold_out_is_reported_before_insufficient_credit():
    m = machine()
    assert m.credit == 0
    assert reason(m, "gum") == "sold_out"


def test_unknown_item_is_reported_before_everything_else():
    m = machine()
    assert reason(m, "") == "unknown_item"


def test_insufficient_credit_is_reported_before_no_change():
    m = VendingMachine({"cola": 100}, {"cola": 1})
    m.insert(25)
    assert reason(m, "cola") == "insufficient_credit"
