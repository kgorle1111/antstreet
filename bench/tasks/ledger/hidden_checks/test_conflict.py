import pytest
from ledger import Ledger


def make():
    ledger = Ledger()
    for name in ("a", "b", "c"):
        ledger.open_account(name)
    ledger.deposit("a", 100, "seed")
    return ledger


def test_same_id_with_another_amount_raises_and_changes_nothing():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    with pytest.raises(ValueError):
        ledger.deposit("a", 20, "t1")
    assert ledger.balance("a") == 110


def test_same_id_with_another_account_raises():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    with pytest.raises(ValueError):
        ledger.deposit("b", 10, "t1")
    assert ledger.balance("b") == 0


def test_the_id_is_shared_between_kinds_of_operation():
    ledger = make()
    ledger.deposit("a", 10, "t1")
    with pytest.raises(ValueError):
        ledger.withdraw("a", 10, "t1")
    assert ledger.balance("a") == 110
    ledger.transfer("a", "b", 10, "t2")
    with pytest.raises(ValueError):
        ledger.withdraw("a", 10, "t2")
    assert ledger.balance("a") == 100


def test_transfer_replay_must_match_both_accounts_and_the_amount():
    ledger = make()
    ledger.transfer("a", "b", 10, "t1")
    for args in (("a", "c", 10), ("b", "a", 10), ("a", "b", 11)):
        with pytest.raises(ValueError):
            ledger.transfer(*args, "t1")
    assert (ledger.balance("a"), ledger.balance("b"), ledger.balance("c")) == (90, 10, 0)


def test_a_conflict_is_reported_before_funds_are_checked():
    ledger = make()
    ledger.deposit("b", 1, "t1")
    with pytest.raises(ValueError):
        ledger.withdraw("b", 10**9, "t1")


def test_the_original_still_replays_after_a_conflict():
    ledger = make()
    assert ledger.deposit("a", 10, "t1") == 110
    with pytest.raises(ValueError):
        ledger.deposit("a", 11, "t1")
    assert ledger.deposit("a", 10, "t1") == 110
    assert ledger.balance("a") == 110
