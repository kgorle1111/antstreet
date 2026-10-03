from math import gcd

import pytest
from fracmath import add, divide, format_fraction, parse_fraction


def reduced(num, den):
    if den < 0:
        num, den = -num, -den
    g = gcd(num, den)
    return num // g, den // g


def test_parsing_the_formatted_value_gives_the_reduced_value_back():
    for num in range(-30, 31):
        for den in list(range(-12, 0)) + list(range(1, 13)):
            assert parse_fraction(format_fraction(num, den)) == reduced(num, den), (num, den)


def test_formatting_a_parsed_text_is_canonical_and_stable():
    texts = [
        "3/4",
        "6/4",
        "-1 1/2",
        "-0 1/2",
        "4/2",
        "0/9",
        "007",
        "1 2/4",
        "10/4",
        "-5/10",
        "  2 1/3 ",
    ]
    for text in texts:
        once = format_fraction(*parse_fraction(text))
        assert format_fraction(*parse_fraction(once)) == once


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("6/4", "1 1/2"),
        ("1 2/4", "1 1/2"),
        ("-0 3/6", "-1/2"),
        ("4/2", "2"),
        ("0/5", "0"),
        ("-0", "0"),
        ("007", "7"),
        ("-10/4", "-2 1/2"),
        ("2 6/8", "2 3/4"),
        ("12/3", "4"),
    ],
)
def test_non_canonical_text_normalises(text, canonical):
    assert format_fraction(*parse_fraction(text)) == canonical


def test_adding_zero_gives_the_canonical_text():
    for text, canonical in (("6/4", "1 1/2"), ("-0 3/6", "-1/2"), ("4/2", "2"), ("-5/10", "-1/2")):
        assert add(text, "0") == canonical


def test_dividing_by_one_gives_the_canonical_text_and_dividing_a_value_by_itself_gives_one():
    for text, canonical in (("6/4", "1 1/2"), ("-0 3/6", "-1/2"), ("4/2", "2")):
        assert divide(text, "1") == canonical
        assert divide(text, text) == "1"


def test_add_and_divide_agree_with_a_plain_integer_model():
    values = [(n, d) for n in range(-6, 7) for d in (1, 2, 3, 4, 6)]
    for an, ad in values:
        for bn, bd in values:
            a, b = format_fraction(an, ad), format_fraction(bn, bd)
            assert parse_fraction(add(a, b)) == reduced(an * bd + bn * ad, ad * bd)
            if bn:
                assert parse_fraction(divide(a, b)) == reduced(an * bd, ad * bn)
