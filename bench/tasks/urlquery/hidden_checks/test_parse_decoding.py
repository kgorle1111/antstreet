import pytest
from urlquery import parse_query


@pytest.mark.parametrize(
    ("qs", "expected"),
    [
        ("a=b+c", {"a": ["b c"]}),
        ("a=b%20c", {"a": ["b c"]}),
        ("a+b=1", {"a b": ["1"]}),
        ("a=%2B", {"a": ["+"]}),
        ("a=1%2B1", {"a": ["1+1"]}),
        ("a=%2b", {"a": ["+"]}),
        ("a=%26%3D%25", {"a": ["&=%"]}),
        ("a=%41%42", {"a": ["AB"]}),
        ("a=%7e%7E", {"a": ["~~"]}),
        ("a=%00", {"a": ["\x00"]}),
    ],
)
def test_plus_and_percent_escapes(qs, expected):
    assert parse_query(qs) == expected


@pytest.mark.parametrize(
    ("qs", "expected"),
    [
        ("a=%C3%A9", {"a": ["é"]}),
        ("a=%c3%a9", {"a": ["é"]}),
        ("a=%E2%82%AC", {"a": ["€"]}),
        ("a=%F0%9F%98%80", {"a": ["\U0001f600"]}),
        ("%C3%A9=1", {"é": ["1"]}),
        ("a=caf%C3%A9+au+lait", {"a": ["café au lait"]}),
    ],
)
def test_percent_escapes_are_utf8(qs, expected):
    assert parse_query(qs) == expected


def test_an_encoded_ampersand_or_equals_does_not_split():
    assert parse_query("a=x%26y%3Dz&b=1") == {"a": ["x&y=z"], "b": ["1"]}
    assert parse_query("k%3Dv=1") == {"k=v": ["1"]}


def test_an_encoded_plus_stays_a_plus_and_a_plus_stays_a_space_together():
    assert parse_query("a=%2B+%2B") == {"a": ["+ +"]}


def test_encoded_question_mark_is_not_a_leading_question_mark():
    assert parse_query("%3Fa=1") == {"?a": ["1"]}
