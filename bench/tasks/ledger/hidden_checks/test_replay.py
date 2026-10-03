import pytest
from ledger import Ledger


def make():
    ledger = Ledger()
    ledger.open_account("a")
    ledger.open_account("b")
    return ledger


def test_replayed_deposit_returns_the_first_result_and_does_nothing():
    ledger = make()
    assert ledger.deposit("a", 100, "t1") == 100
    assert ledger.deposit("a", 50, "t2") == 150
    assert ledger.deposit("a", 100, "t1") == 100
    assert ledger.balance("a") == 150


def test_replayed_withdraw_returns_the_first_result_and_does_nothing():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    assert ledger.withdraw("a", 30, "t2") == 70
    ledger.deposit("a", 500, "t3")
    assert ledger.withdraw("a", 30, "t2") == 70
    assert ledger.balance("a") == 570


def test_replayed_transfer_returns_the_first_source_balance():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    assert ledger.transfer("a", "b", 30, "t2") == 70
    ledger.deposit("a", 1000, "t3")
    assert ledger.transfer("a", "b", 30, "t2") == 70
    assert ledger.balance("a") == 1070
    assert ledger.balance("b") == 30


def test_replay_succeeds_even_when_the_funds_are_gone():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    assert ledger.withdraw("a", 100, "t2") == 0
    assert ledger.withdraw("a", 100, "t2") == 0
    assert ledger.balance("a") == 0


def test_many_replays_apply_once():
    ledger = make()
    for _ in range(10):
        assert ledger.deposit("a", 7, "same") == 7
    assert ledger.balance("a") == 7
    assert ledger.statement("a") == [("same", 7)]


def test_replay_checks_the_account_exists_first():
    ledger = make()
    ledger.deposit("a", 5, "t1")
    with pytest.raises(KeyError):
        ledger.deposit("ghost", 5, "t1")
