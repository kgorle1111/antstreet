import pytest
from luhn import is_valid


@pytest.mark.parametrize(
    "number",
    [
        "79927398713",  # 11 digits
        "4539148803436467",  # 16 digits
        "4111111111111111",
        "378282246310005",  # 15 digits
        "5500000000000004",
        "6011111111111117",
        "3530111333300000",
        "49927398716",
        "1234567812345670",
        "4012888888881881",
        "371449635398431",
        "30569309025904",  # 14 digits
        "109",
        "190",
        "901",
        "18",
        "00",
        "0000",
        "0000000000000000",
    ],
)
def test_valid_numbers(number):
    assert is_valid(number) is True


@pytest.mark.parametrize("number", ["79927398710", "4111111111111112", "1111", "123", "12345678"])
def test_invalid_numbers(number):
    assert is_valid(number) is False


def test_the_result_is_a_real_bool():
    assert type(is_valid("79927398713")) is bool
    assert type(is_valid("79927398710")) is bool
    assert type(is_valid("abc")) is bool
    assert type(is_valid("")) is bool


def test_odd_and_even_lengths_both_double_from_the_right():
    # 3 digits: only the middle one is doubled (1 + 0 + 9, 1 + 9 + 0, 9 + 2 + 0)
    assert is_valid("109")
    assert is_valid("190")
    assert not is_valid("910")
    # 4 digits: the first and third are doubled (2 + 2 + 6 + 0, 0 + 0 + 1 + 9, 1 + 9 + 0 + 0)
    assert is_valid("1230")
    assert is_valid("0059")
    assert is_valid("5900")
    assert not is_valid("9500")
    # 5 digits: the second and fourth are doubled
    assert is_valid("00018")
    assert is_valid("10009")
    assert not is_valid("18000")
