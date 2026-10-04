import pytest
from ledger import InsufficientFunds, Ledger


def test_new_account_has_a_zero_balance():
    ledger = Ledger()
    ledger.open_account("alice")
    assert ledger.balance("alice") == 0
    assert ledger.open_account("bob", overdraft=500) is None
    assert ledger.balance("bob") == 0


def test_opening_an_existing_name_raises_and_changes_nothing():
    ledger = Ledger()
    ledger.open_account("alice", overdraft=10)
    ledger.deposit("alice", 70, "t1")
    with pytest.raises(ValueError):
        ledger.open_account("alice", overdraft=999)
    assert ledger.balance("alice") == 70
    assert ledger.statement("alice") == [("t1", 70)]
    assert ledger.withdraw("alice", 80, "t2") == -10
    with pytest.raises(InsufficientFunds):
        ledger.withdraw("alice", 1, "t3")


@pytest.mark.parametrize("name", ["", None, 5, b"alice"])
def test_bad_account_name_raises(name):
    with pytest.raises(ValueError):
        Ledger().open_account(name)


@pytest.mark.parametrize("overdraft", [-1, -100, 1.5, "10", None])
def test_bad_overdraft_raises(overdraft):
    ledger = Ledger()
    with pytest.raises(ValueError):
        ledger.open_account("alice", overdraft=overdraft)
    with pytest.raises(KeyError):
        ledger.balance("alice")


def test_unknown_account_has_no_balance_or_statement():
    ledger = Ledger()
    with pytest.raises(KeyError):
        ledger.balance("ghost")
    with pytest.raises(KeyError):
        ledger.statement("ghost")


def test_accounts_are_independent():
    ledger = Ledger()
    ledger.open_account("a")
    ledger.open_account("b")
    ledger.deposit("a", 10, "t1")
    assert ledger.balance("a") == 10
    assert ledger.balance("b") == 0
    other = Ledger()
    with pytest.raises(KeyError):
        other.balance("a")
