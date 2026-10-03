from vending import VendingMachine


def test_refund_returns_the_same_coins_largest_first():
    m = VendingMachine({"cola": 100}, {"cola": 1})
    for coin in (25, 5, 25, 10, 25):
        m.insert(coin)
    assert m.refund() == [25, 25, 25, 10, 5]
    assert m.credit == 0


def test_refund_does_not_re_make_the_amount():
    m = VendingMachine({"cola": 100}, {"cola": 1}, change={100: 9})
    for _ in range(4):
        m.insert(25)
    assert m.refund() == [25, 25, 25, 25]


def test_refund_with_nothing_inserted_is_empty():
    m = VendingMachine({"cola": 100}, {"cola": 1})
    assert m.refund() == []
    assert m.refund() == []


def test_refunded_coins_never_reach_the_float():
    m = VendingMachine({"cola": 100}, {"cola": 1})
    m.insert(25)
    m.insert(100)
    m.refund()
    assert m.coins() == {5: 0, 10: 0, 25: 0, 100: 0}


def test_refund_after_a_sale_returns_nothing():
    m = VendingMachine({"gum": 25}, {"gum": 1})
    m.insert(25)
    m.select("gum")
    assert m.refund() == []


def test_refund_empties_the_credit_for_the_next_session():
    m = VendingMachine({"gum": 25}, {"gum": 1})
    m.insert(25)
    m.refund()
    m.insert(5)
    assert m.credit == 5
    assert m.refund() == [5]
