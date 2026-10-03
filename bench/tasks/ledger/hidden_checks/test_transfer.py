import pytest
from ledger import InsufficientFunds, Ledger


def make(**overdrafts):
    ledger = Ledger()
    for name in ("a", "b", "c"):
        ledger.open_account(name, overdraft=overdrafts.get(name, 0))
    return ledger


def test_transfer_moves_money_and_returns_the_source_balance():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    assert ledger.transfer("a", "b", 30, "t2") == 70
    assert ledger.balance("a") == 70
    assert ledger.balance("b") == 30
    assert ledger.balance("c") == 0


def test_transfer_may_overdraw_the_source_up_to_its_limit():
    ledger = make(a=50)
    assert ledger.transfer("a", "b", 50, "t1") == -50
    with pytest.raises(InsufficientFunds):
        ledger.transfer("a", "b", 1, "t2")
    assert ledger.balance("a") == -50
    assert ledger.balance("b") == 50


def test_refused_transfer_changes_neither_account():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    ledger.deposit("b", 5, "t2")
    with pytest.raises(InsufficientFunds):
        ledger.transfer("a", "b", 11, "t3")
    assert (ledger.balance("a"), ledger.balance("b")) == (10, 5)
    assert ledger.statement("a") == [("t1", 10)]
    assert ledger.statement("b") == [("t2", 5)]


def test_transfer_to_the_same_account_raises():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    with pytest.raises(ValueError):
        ledger.transfer("a", "a", 5, "t2")
    assert ledger.balance("a") == 10
    assert ledger.deposit("a", 1, "t2") == 11


def test_unknown_destination_or_source_raises_and_changes_nothing():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    with pytest.raises(KeyError):
        ledger.transfer("a", "ghost", 5, "t2")
    assert ledger.balance("a") == 10
    assert ledger.statement("a") == [("t1", 10)]
    with pytest.raises(KeyError):
        ledger.transfer("ghost", "a", 5, "t3")
    assert ledger.balance("a") == 10


def test_transfer_into_an_overdrawn_account_is_allowed():
    ledger = make(b=40)
    ledger.withdraw("b", 40, "t1")
    ledger.deposit("c", 25, "t3")
    assert ledger.transfer("c", "b", 25, "t4") == 0
    assert ledger.balance("b") == -15


def test_total_money_is_conserved_by_transfers():
    ledger = make(a=1000, b=1000, c=1000)
    ledger.deposit("a", 500, "d1")
    moves = [("a", "b", 300), ("b", "c", 700), ("c", "a", 1200), ("a", "c", 99)]
    for i, (src, dst, amount) in enumerate(moves):
        ledger.transfer(src, dst, amount, f"m{i}")
    assert sum(ledger.balance(n) for n in "abc") == 500
