import pytest
from ledger import InsufficientFunds, Ledger


def make():
    ledger = Ledger()
    ledger.open_account("a")
    ledger.open_account("b")
    return ledger


def test_a_refused_withdrawal_can_be_retried_with_the_same_id():
    ledger = make()
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("a", 50, "t1")
    ledger.deposit("a", 80, "t2")
    assert ledger.withdraw("a", 50, "t1") == 30
    assert ledger.balance("a") == 30


def test_a_refused_id_may_be_used_for_a_different_operation():
    ledger = make()
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("a", 50, "t1")
    assert ledger.deposit("b", 7, "t1") == 7
    assert ledger.balance("b") == 7


def test_a_refused_transfer_can_be_retried_with_the_same_id():
    ledger = make()
    with pytest.raises(InsufficientFunds):
        ledger.transfer("a", "b", 50, "t1")
    ledger.deposit("a", 60, "t2")
    assert ledger.transfer("a", "b", 50, "t1") == 10
    assert ledger.balance("b") == 50


def test_refusing_twice_in_a_row_is_still_a_refusal():
    ledger = make()
    for _ in range(3):
        with pytest.raises(InsufficientFunds):
            ledger.withdraw("a", 50, "t1")
    assert ledger.statement("a") == []


def test_a_malformed_call_does_not_use_up_its_id():
    ledger = make()
    with pytest.raises(ValueError):
        ledger.deposit("a", 0, "t1")
    with pytest.raises(KeyError):
        ledger.deposit("ghost", 5, "t1")
    assert ledger.deposit("a", 5, "t1") == 5
