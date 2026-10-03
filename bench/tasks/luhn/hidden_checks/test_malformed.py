import pytest
from luhn import is_valid


@pytest.mark.parametrize("text", ["", " ", "   ", "-", "--", " - ", "- -", "\t", "\n"])
def test_text_with_no_digits_is_false(text):
    assert is_valid(text) is False


@pytest.mark.parametrize("text", ["0", "5", "9", " 0 ", "-0-", "0 ", "1", "8", "- 5"])
def test_a_single_digit_is_false_even_when_its_sum_is_a_multiple_of_ten(text):
    assert is_valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "4111111111111111a",
        "a4111111111111111",
        "41111111x1111111",
        "abcd",
        "79927398713 abc",
        "7992739871e3",
        "0x79927398713",
        "4111111111111111!",
        "(4111111111111111)",
        "79927398713.0",
        "7992739871３",
    ],
)
def test_letters_and_symbols_make_it_false(text):
    assert is_valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "٠٠",  # Arabic-Indic 00
        "١٨",  # Arabic-Indic 18
        "１８",  # full-width 18
        "00٠",
        "18०",  # Devanagari zero after an ASCII 18
        "४１११１１１１１１１１１１１１１",
        "²³",
        "①⑧",
    ],
)
def test_digits_of_other_scripts_are_not_digits(text):
    assert is_valid(text) is False


def test_it_never_raises_for_any_string():
    for text in ["", "!", "\x00", "💳", "9" * 500, "-" * 500, "0" * 500, " " * 3 + "1"]:
        assert isinstance(is_valid(text), bool)


def test_a_very_long_valid_number():
    assert is_valid("0" * 500) is True
    assert is_valid("0" * 499 + "1") is False
    assert is_valid("0" * 498 + "18") is True


@pytest.mark.parametrize(
    "value", [None, 79927398713, 1.5, b"79927398713", ["79927398713"], True, 0]
)
def test_non_string_input_is_a_type_error(value):
    with pytest.raises(TypeError):
        is_valid(value)
