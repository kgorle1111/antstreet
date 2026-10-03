import pytest
from httpheaders import parse_headers


@pytest.mark.parametrize(
    "text",
    [
        "no colon here",
        "A",
        "A: 1\r\nB",
        "A: 1\r\nbroken line\r\nC: 3",
        "\x00",
    ],
)
def test_a_line_without_a_colon_is_an_error(text):
    with pytest.raises(ValueError):
        parse_headers(text)


@pytest.mark.parametrize("text", [":x", ": x", ":", "A: 1\r\n:x", "A: 1\r\n: x\r\nB: 2"])
def test_an_empty_name_is_an_error(text):
    with pytest.raises(ValueError):
        parse_headers(text)


@pytest.mark.parametrize(
    "text",
    [
        "Name : x",
        "Name  : x",
        "Name\t: x",
        "My Name: x",
        "A: 1\r\nBad Name: 2",
        "Na(me: x",
        "Na)me: x",
        "Na/me: x",
        "Na@me: x",
        'Na"me: x',
        "Na;me: x",
        "Na,me: x",
        "Na[me: x",
        "Na{me: x",
        "Na\\me: x",
        "Na=me: x",
        "Na<me: x",
        "Na?me: x",
        "Né: x",
        "中: x",
        "A\r: x",
    ],
)
def test_a_name_with_a_character_that_is_not_allowed_is_an_error(text):
    with pytest.raises(ValueError):
        parse_headers(text)


def test_the_first_bad_line_decides_even_after_good_ones():
    with pytest.raises(ValueError):
        parse_headers("A: 1\r\nB: 2\r\nC 3\r\nD: 4")


def test_a_bad_line_after_the_empty_line_is_not_an_error():
    assert parse_headers("A: 1\r\n\r\nC 3").items() == [("A", "1")]


def test_a_bad_continuation_still_needs_a_header_above_it():
    with pytest.raises(ValueError):
        parse_headers(" continuation first\r\nA: 1")
