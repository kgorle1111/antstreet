import pytest
from exprtokens import tokenize


@pytest.mark.parametrize("text", ["0", "7", "12", "007", "3.5", "0.25", ".5", ".05", "10.000"])
def test_plain_numbers_are_one_token(text):
    assert tokenize(text) == [("NUM", text, 0)]


@pytest.mark.parametrize(
    "text", ["1e5", "1E5", "2.5e3", "2.5E-3", "1e+10", "1e-1", ".5e2", "10e00", "3e007"]
)
def test_numbers_with_a_complete_exponent_are_one_token(text):
    assert tokenize(text) == [("NUM", text, 0)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2e", [("NUM", "2", 0), ("IDENT", "e", 1)]),
        ("2E", [("NUM", "2", 0), ("IDENT", "E", 1)]),
        ("2e+", [("NUM", "2", 0), ("IDENT", "e", 1), ("OP", "+", 2)]),
        ("2e-x", [("NUM", "2", 0), ("IDENT", "e", 1), ("OP", "-", 2), ("IDENT", "x", 3)]),
        ("1.5e", [("NUM", "1.5", 0), ("IDENT", "e", 3)]),
        ("2ex", [("NUM", "2", 0), ("IDENT", "ex", 1)]),
        ("2e5x", [("NUM", "2e5", 0), ("IDENT", "x", 3)]),
    ],
)
def test_an_incomplete_exponent_is_not_part_of_the_number(text, expected):
    assert tokenize(text) == expected


def test_a_number_runs_into_an_identifier_without_a_separator():
    assert tokenize("2x") == [("NUM", "2", 0), ("IDENT", "x", 1)]
    assert tokenize("3pi") == [("NUM", "3", 0), ("IDENT", "pi", 1)]


def test_longest_match_splits_a_second_fraction_into_a_new_number():
    assert tokenize("1.5.2") == [("NUM", "1.5", 0), ("NUM", ".2", 3)]
    assert tokenize("1.2.3.4") == [("NUM", "1.2", 0), ("NUM", ".3", 3), ("NUM", ".4", 5)]


def test_two_numbers_separated_by_space_are_two_tokens():
    assert tokenize("12 34") == [("NUM", "12", 0), ("NUM", "34", 3)]


def test_a_number_has_no_sign():
    assert tokenize("-5") == [("OP", "-", 0), ("NUM", "5", 1)]
    assert tokenize("+.5") == [("OP", "+", 0), ("NUM", ".5", 1)]
    assert tokenize("3-2") == [("NUM", "3", 0), ("OP", "-", 1), ("NUM", "2", 2)]
    assert tokenize("1e-2-1") == [("NUM", "1e-2", 0), ("OP", "-", 4), ("NUM", "1", 5)]


def test_a_dot_must_be_followed_by_a_digit_inside_a_number():
    assert tokenize("5 .5") == [("NUM", "5", 0), ("NUM", ".5", 2)]
