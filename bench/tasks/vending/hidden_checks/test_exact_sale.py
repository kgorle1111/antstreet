from vending import VendingMachine


def test_exact_money_gives_the_item_and_no_change():
    m = VendingMachine({"cola": 125}, {"cola": 3})
    m.insert(100)
    m.insert(25)
    assert m.select("cola") == ("cola", [])
    assert m.credit == 0
    assert m.remaining("cola") == 2


def test_inserted_coins_join_the_float_after_a_sale():
    m = VendingMachine({"gum": 35}, {"gum": 1})
    for coin in (25, 10):
        m.insert(coin)
    m.select("gum")
    assert m.coins() == {5: 0, 10: 1, 25: 1, 100: 0}


def test_returns_a_tuple_and_a_list():
    m = VendingMachine({"gum": 5}, {"gum": 1})
    m.insert(5)
    result = m.select("gum")
    assert isinstance(result, tuple)
    assert isinstance(result[1], list)


def test_new_session_after_a_sale_starts_from_zero():
    m = VendingMachine({"gum": 5}, {"gum": 2})
    m.insert(5)
    m.select("gum")
    assert m.credit == 0
    m.insert(10)
    assert m.credit == 10
    assert m.refund() == [10]
