import pytest
from ledger import InsufficientFunds, Ledger


def make():
    ledger = Ledger()
    ledger.open_account("a", overdraft=10)
    ledger.open_account("b")
    return ledger


def test_new_account_has_an_empty_statement():
    assert make().statement("a") == []


def test_entries_are_signed_deltas_in_order():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    ledger.withdraw("a", 30, "t2")
    ledger.transfer("a", "b", 20, "t3")
    ledger.transfer("b", "a", 5, "t4")
    assert ledger.statement("a") == [("t1", 100), ("t2", -30), ("t3", -20), ("t4", 5)]
    assert ledger.statement("b") == [("t3", 20), ("t4", -5)]


def test_replays_and_refusals_add_nothing():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    ledger.deposit("a", 100, "t1")
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("b", 1, "t2")
    with pytest.raises(ValueError):
        ledger.deposit("a", 1, "t1")
    with pytest.raises(ValueError):
        ledger.deposit("a", 0, "t3")
    assert ledger.statement("a") == [("t1", 100)]
    assert ledger.statement("b") == []


def test_statement_is_a_copy():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    ledger.statement("a").append(("x", 1))
    assert ledger.statement("a") == [("t1", 10)]


def test_statement_deltas_add_up_to_the_balance():
    ledger = make()
    ledger.deposit("a", 100, "t1")
    ledger.withdraw("a", 105, "t2")
    ledger.transfer("a", "b", 3, "t3")
    assert sum(d for _, d in ledger.statement("a")) == ledger.balance("a")
    assert sum(d for _, d in ledger.statement("b")) == ledger.balance("b")


def test_entries_are_tuples_of_id_and_int():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    (entry,) = ledger.statement("a")
    assert isinstance(entry, tuple)
    assert entry == ("t1", 10)
