from ledger import Ledger


def make():
    ledger = Ledger()
    ledger.open_account("a")
    ledger.open_account("b")
    return ledger


def test_deposit_returns_the_new_balance():
    ledger = make()
    assert ledger.deposit("a", 100, "t1") == 100
    assert ledger.deposit("a", 50, "t2") == 150
    assert ledger.balance("a") == 150
    assert ledger.balance("b") == 0


def test_withdraw_returns_the_new_balance():
    ledger = make()
    ledger.deposit("a", 150, "t1")
    assert ledger.withdraw("a", 30, "t2") == 120
    assert ledger.balance("a") == 120


def test_withdraw_the_whole_balance():
    ledger = make()
    ledger.deposit("a", 40, "t1")
    assert ledger.withdraw("a", 40, "t2") == 0
    assert ledger.balance("a") == 0


def test_one_cent_amounts_and_large_amounts():
    ledger = make()
    assert ledger.deposit("a", 1, "t1") == 1
    assert ledger.deposit("a", 10**15, "t2") == 10**15 + 1
    assert ledger.withdraw("a", 10**15, "t3") == 1


def test_many_operations_add_up():
    ledger = make()
    for i in range(1, 51):
        ledger.deposit("a", i, f"d{i}")
    for i in range(1, 11):
        ledger.withdraw("a", i, f"w{i}")
    assert ledger.balance("a") == sum(range(1, 51)) - sum(range(1, 11))
