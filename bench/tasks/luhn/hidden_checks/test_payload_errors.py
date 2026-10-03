import pytest
from luhn import check_digit, with_check_digit

BAD_PAYLOADS = [
    "",
    " ",
    "   ",
    "-",
    "--",
    " - - ",
    "12a",
    "a12",
    "1 2 x",
    "12.5",
    "+12",
    "1\t2",
    "12\n",
    "1_2",
    "١٢",
    "１２",
    "12٣",
    "²",
    "abc",
    "💳",
]


@pytest.mark.parametrize("payload", BAD_PAYLOADS)
def test_a_payload_without_digits_or_with_other_characters_is_a_value_error(payload):
    with pytest.raises(ValueError):
        check_digit(payload)
    with pytest.raises(ValueError):
        with_check_digit(payload)


@pytest.mark.parametrize("value", [None, 7992739871, 1.5, b"7992739871", ["7992739871"], True, 0])
def test_a_payload_that_is_not_a_str_is_a_type_error(value):
    with pytest.raises(TypeError):
        check_digit(value)
    with pytest.raises(TypeError):
        with_check_digit(value)


def test_one_digit_is_enough_for_a_payload():
    assert check_digit("0") == 0
    assert with_check_digit("0") == "00"
    assert check_digit(" 0 ") == 0
    assert with_check_digit("-0-") == "00"


def test_valid_calls_still_work_after_the_errors():
    assert check_digit("0") == 0
    assert with_check_digit("00") == "000"
