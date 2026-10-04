from vending import VendingMachine


def test_change_is_made_largest_coin_first():
    m = VendingMachine({"chips": 65}, {"chips": 1}, change={25: 4, 10: 4, 5: 4})
    m.insert(100)
    assert m.select("chips") == ("chips", [25, 10])
    assert m.coins() == {5: 4, 10: 3, 25: 3, 100: 1}


def test_larger_change_takes_the_biggest_coins_it_can():
    m = VendingMachine({"chips": 5}, {"chips": 1}, change={100: 1, 25: 5, 10: 5, 5: 5})
    for _ in range(2):
        m.insert(100)
    assert m.select("chips") == ("chips", [100, 25, 25, 25, 10, 10])
    assert m.coins() == {5: 5, 10: 3, 25: 2, 100: 2}


def test_change_falls_back_to_smaller_coins_when_a_size_runs_out():
    m = VendingMachine({"chips": 50}, {"chips": 1}, change={25: 1, 10: 3, 5: 1})
    m.insert(100)
    assert m.select("chips") == ("chips", [25, 10, 10, 5])
    assert m.coins() == {5: 0, 10: 1, 25: 0, 100: 1}


def test_change_never_uses_a_coin_the_machine_does_not_have():
    m = VendingMachine({"chips": 90}, {"chips": 1}, change={10: 1})
    m.insert(100)
    assert m.select("chips") == ("chips", [10])
    assert m.coins() == {5: 0, 10: 0, 25: 0, 100: 1}


def test_float_after_sale_adds_inserted_and_removes_change():
    m = VendingMachine({"chips": 65}, {"chips": 2}, change={10: 1, 25: 1})
    m.insert(100)
    assert m.select("chips") == ("chips", [25, 10])
    assert m.coins() == {5: 0, 10: 0, 25: 0, 100: 1}
    assert m.remaining("chips") == 1
