import pytest
from calc import evaluate


def test_subtraction_is_left_associative():
    assert evaluate("10 - 4 - 3") == 3
    assert evaluate("10 - 4 - 3 - 2") == 1
    assert evaluate("1 - 2 - 3") == -4
    assert evaluate("1 - 2 + 3") == 2
    assert evaluate("10 - 3 + 2 - 1") == 8


def test_division_is_left_associative():
    assert evaluate("100 / 10 / 5") == pytest.approx(2.0)
    assert evaluate("24 / 4 / 3") == pytest.approx(2.0)
    assert evaluate("8 / 4 / 2") == pytest.approx(1.0)
    assert evaluate("2 / 4 / 2") == pytest.approx(0.25)


def test_mixed_multiplication_and_division_go_left_to_right():
    assert evaluate("2 * 3 / 4") == pytest.approx(1.5)
    assert evaluate("2 / 4 * 3") == pytest.approx(1.5)
    assert evaluate("8 / 2 * 4") == pytest.approx(16.0)
    assert evaluate("8 / (2 * 4)") == pytest.approx(1.0)
    assert evaluate("1 / 2 / 2 * 8") == pytest.approx(2.0)


def test_long_chains_do_not_blow_the_stack():
    assert evaluate("+".join(["1"] * 2000)) == 2000
    assert evaluate("-".join(["1"] * 2001)) == 1 - 2000
    assert evaluate("*".join(["1"] * 2000)) == 1
    assert evaluate("1" + " + 1 - 1" * 1000) == 1


def test_long_alternating_chain_keeps_left_to_right_order():
    text = "1000" + "".join(f" - {n}" for n in range(1, 101))
    assert evaluate(text) == 1000 - sum(range(1, 101))
    assert evaluate("1024" + " / 2" * 10) == pytest.approx(1.0)
