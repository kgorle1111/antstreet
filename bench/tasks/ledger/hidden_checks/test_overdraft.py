import pytest
from ledger import InsufficientFunds, Ledger


def test_no_overdraft_means_the_balance_cannot_go_below_zero():
    ledger = Ledger()
    ledger.open_account("a")
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("a", 1, "t1")
    ledger.deposit("a", 10, "t2")
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("a", 11, "t3")
    assert ledger.balance("a") == 10


def test_balance_exactly_minus_overdraft_is_allowed_one_cent_more_is_not():
    ledger = Ledger()
    ledger.open_account("a", overdraft=100)
    assert ledger.withdraw("a", 100, "t1") == -100
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("a", 1, "t2")
    assert ledger.balance("a") == -100


def test_the_limit_counts_from_the_current_balance():
    ledger = Ledger()
    ledger.open_account("a", overdraft=20)
    ledger.deposit("a", 50, "t1")
    assert ledger.withdraw("a", 70, "t2") == -20
    ledger2 = Ledger()
    ledger2.open_account("a", overdraft=20)
    ledger2.deposit("a", 50, "t1")
    with pytest.raises(InsufficientFunds):
        ledger2.withdraw("a", 71, "t2")
    assert ledger2.balance("a") == 50


def test_deposit_into_an_overdrawn_account_is_never_refused():
    ledger = Ledger()
    ledger.open_account("a", overdraft=100)
    ledger.withdraw("a", 100, "t1")
    assert ledger.deposit("a", 30, "t2") == -70
    assert ledger.deposit("a", 1, "t3") == -69


def test_refusal_changes_nothing_and_is_not_a_statement_entry():
    ledger = Ledger()
    ledger.open_account("a", overdraft=5)
    ledger.deposit("a", 10, "t1")
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("a", 16, "t2")
    assert ledger.balance("a") == 10
    assert ledger.statement("a") == [("t1", 10)]


def test_each_account_has_its_own_limit():
    ledger = Ledger()
    ledger.open_account("a", overdraft=50)
    ledger.open_account("b")
    ledger.withdraw("a", 50, "t1")
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("b", 1, "t2")
