import pytest
from ledger import Ledger


def make():
    ledger = Ledger()
    ledger.open_account("a", overdraft=100)
    ledger.open_account("b")
    ledger.deposit("a", 50, "seed")
    return ledger


@pytest.mark.parametrize("amount", [0, -5, 1.5, "5", None])
def test_bad_amount_raises_for_every_operation(amount):
    ledger = make()
    with pytest.raises(ValueError):
        ledger.deposit("a", amount, "t1")
    with pytest.raises(ValueError):
        ledger.withdraw("a", amount, "t2")
    with pytest.raises(ValueError):
        ledger.transfer("a", "b", amount, "t3")
    assert ledger.balance("a") == 50
    assert ledger.balance("b") == 0


@pytest.mark.parametrize("txn_id", ["", None, 7, b"x"])
def test_bad_txn_id_raises_for_every_operation(txn_id):
    ledger = make()
    with pytest.raises(ValueError):
        ledger.deposit("a", 5, txn_id)
    with pytest.raises(ValueError):
        ledger.withdraw("a", 5, txn_id)
    with pytest.raises(ValueError):
        ledger.transfer("a", "b", 5, txn_id)
    assert ledger.balance("a") == 50


def test_unknown_accounts_raise_key_error_for_every_operation():
    ledger = make()
    with pytest.raises(KeyError):
        ledger.deposit("ghost", 5, "t1")
    with pytest.raises(KeyError):
        ledger.withdraw("ghost", 5, "t2")
    with pytest.raises(KeyError):
        ledger.transfer("ghost", "b", 5, "t3")
    with pytest.raises(KeyError):
        ledger.transfer("a", "ghost", 5, "t4")
    assert ledger.balance("a") == 50


def test_malformed_arguments_are_reported_before_a_missing_account():
    ledger = make()
    with pytest.raises(ValueError):
        ledger.deposit("ghost", 0, "t1")
    with pytest.raises(ValueError):
        ledger.withdraw("ghost", 5, "")
    with pytest.raises(ValueError):
        ledger.transfer("ghost", "ghost", 5, "t2")


def test_a_missing_account_is_reported_before_funds():
    ledger = make()
    with pytest.raises(KeyError):
        ledger.withdraw("ghost", 10**9, "t1")
    with pytest.raises(KeyError):
        ledger.transfer("a", "ghost", 10**9, "t2")


def test_smallest_valid_arguments_are_accepted():
    ledger = make()
    assert ledger.deposit("b", 1, "x") == 1
    assert ledger.withdraw("b", 1, "y") == 0
    assert ledger.transfer("a", "b", 1, "z") == 49
