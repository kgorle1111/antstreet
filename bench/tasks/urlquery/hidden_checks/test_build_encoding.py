import string

import pytest
from urlquery import build_query


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"a": "1"}, "a=1"),
        ({"a b": "c d"}, "a+b=c+d"),
        ({"q": "a b&c"}, "q=a+b%26c"),
        ({"q": "é"}, "q=%C3%A9"),
        ({"q": "€"}, "q=%E2%82%AC"),
        ({"q": "\U0001f600"}, "q=%F0%9F%98%80"),
        ({"q": "+"}, "q=%2B"),
        ({"q": "1+1=2"}, "q=1%2B1%3D2"),
        ({"q": "100%"}, "q=100%25"),
        ({"k=v&x": "1"}, "k%3Dv%26x=1"),
        ({"q": "a/b?c#d"}, "q=a%2Fb%3Fc%23d"),
        ({"q": "\n\t"}, "q=%0A%09"),
        ({"q": "\x00\x7f"}, "q=%00%7F"),
    ],
)
def test_encoding(params, expected):
    assert build_query(params) == expected


def test_unreserved_characters_are_written_as_they_are():
    safe = string.ascii_letters + string.digits + "-._~"
    assert build_query({"k": safe}) == "k=" + safe


def test_every_other_ascii_character_is_percent_encoded_in_uppercase_hex():
    safe = set(string.ascii_letters + string.digits + "-._~")
    for code in range(128):
        ch = chr(code)
        expected = ch if ch in safe else "+" if ch == " " else f"%{code:02X}"
        assert build_query({"k": ch}) == "k=" + expected, repr(ch)


def test_hex_digits_are_uppercase():
    assert build_query({"k": "\xff\xfe"}) == "k=%C3%BF%C3%BE"
    assert build_query({"k": "~«"}) == "k=~%C2%AB"


def test_keys_are_encoded_like_values():
    assert build_query({"a&b": "x", "é": "y"}) == "a%26b=x&%C3%A9=y"
