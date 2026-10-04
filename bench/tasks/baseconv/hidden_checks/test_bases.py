import pytest
from baseconv import convert, parse_number


@pytest.mark.parametrize("bad", [0, 1, 37, 100, -2, -10])
def test_a_base_outside_two_to_thirty_six_raises_value_error(bad):
    with pytest.raises(ValueError):
        parse_number("1", bad)
    with pytest.raises(ValueError):
        convert("1", bad, 10)
    with pytest.raises(ValueError):
        convert("1", 10, bad)


@pytest.mark.parametrize("bad", [2.0, 10.5, "10", None, True, False, [10]])
def test_a_base_that_is_not_an_int_raises_type_error(bad):
    with pytest.raises(TypeError):
        parse_number("1", bad)
    with pytest.raises(TypeError):
        convert("1", bad, 10)
    with pytest.raises(TypeError):
        convert("1", 10, bad)


def test_bases_two_and_thirty_six_are_accepted():
    assert convert("101", 2, 36) == "5"
    assert convert("5", 36, 2) == "101"
    assert parse_number("z", 36) == 35


def test_a_bad_to_base_is_an_error_even_for_a_number_that_is_zero():
    with pytest.raises(ValueError):
        convert("0", 10, 1)
    with pytest.raises(ValueError):
        convert("0", 10, 37)


@pytest.mark.parametrize("bad", [-1, -100])
def test_a_negative_max_frac_raises_value_error(bad):
    with pytest.raises(ValueError):
        convert("0.5", 10, 2, bad)
    with pytest.raises(ValueError):
        convert("5", 10, 2, bad)


@pytest.mark.parametrize("bad", [1.0, 2.5, "3", None, True, False, [3]])
def test_a_max_frac_that_is_not_an_int_raises_type_error(bad):
    with pytest.raises(TypeError):
        convert("0.5", 10, 2, bad)
    with pytest.raises(TypeError):
        convert("5", 10, 2, bad)


def test_a_max_frac_of_zero_is_fine():
    assert convert("5.5", 10, 2, 0) == "101"
