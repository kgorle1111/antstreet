import pytest
from luhn import is_valid


@pytest.mark.parametrize(
    "text",
    [
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "4111  1111   1111 1111",
        "4111--1111--1111--1111",
        "4111 - 1111 - 1111 - 1111",
        "4 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1",
        "4-1-1-1-1-1-1-1-1-1-1-1-1-1-1-1",
        "  4111111111111111  ",
        "-4111111111111111-",
        " - 4111111111111111 - ",
        "4111111111111111 ",
        " 4111111111111111",
        "41111111 11111111",
    ],
)
def test_spaces_and_hyphens_are_ignored_anywhere(text):
    assert is_valid(text) is True


@pytest.mark.parametrize(
    "text",
    ["4111 1111 1111 1112", "4111-1111-1111-1112", "  4111111111111112  ", "7992 7398 710"],
)
def test_separators_do_not_make_a_bad_number_valid(text):
    assert is_valid(text) is False


@pytest.mark.parametrize(
    ("text", "valid"),
    [
        ("7992 7398 713", True),
        ("79927-39871-3", True),
        ("1 8", True),
        ("1-8", True),
        (" 1 8 ", True),
        ("0 0", True),
        ("0-0", True),
        ("5 9", True),
        ("1 9", False),
    ],
)
def test_short_numbers_with_separators(text, valid):
    assert is_valid(text) is valid


@pytest.mark.parametrize(
    "text",
    [
        "4111\t1111\t1111\t1111",
        "4111\n1111 1111 1111",
        "4111111111111111\n",
        "\t4111111111111111",
        "4111.1111.1111.1111",
        "4111_1111_1111_1111",
        "4111/1111/1111/1111",
        "4111,1111,1111,1111",
        "+4111111111111111",
        "4111111111111111\x00",
        "4111 1111 1111 1111",
        "4111‑1111‑1111‑1111",
    ],
)
def test_other_separators_are_invalid_characters(text):
    assert is_valid(text) is False
