import pytest
from httpheaders import parse_headers


def test_simple_headers_in_text_order():
    h = parse_headers("Host: example.com\r\nAccept: */*\r\nX-Id: 7\r\n")
    assert h.items() == [("Host", "example.com"), ("Accept", "*/*"), ("X-Id", "7")]
    assert len(h) == 3


@pytest.mark.parametrize(
    "text",
    [
        "A: 1\r\nB: 2\r\n",
        "A: 1\nB: 2\n",
        "A: 1\r\nB: 2\n",
        "A: 1\nB: 2\r\n",
        "A: 1\r\nB: 2",
        "A: 1\nB: 2",
        "A: 1\r\nB: 2\r\n\r\n",
        "A: 1\nB: 2\n\n",
    ],
)
def test_line_endings_are_lf_or_crlf_in_any_mix(text):
    assert parse_headers(text).items() == [("A", "1"), ("B", "2")]


@pytest.mark.parametrize(
    ("line", "value"),
    [
        ("A:x", "x"),
        ("A: x", "x"),
        ("A:    x", "x"),
        ("A:\tx", "x"),
        ("A: \t x \t ", "x"),
        ("A: x   ", "x"),
        ("A: two words  inside", "two words  inside"),
        ("A:", ""),
        ("A:   ", ""),
        ("A:\t", ""),
    ],
)
def test_the_value_is_stripped_of_spaces_and_tabs_only(line, value):
    assert parse_headers(line).items() == [("A", value)]


def test_the_value_may_contain_more_colons():
    h = parse_headers("Host: example.com:8080\r\nDate: Tue, 15 Nov 1994 08:12:31 GMT\r\nX: a:b:c:")
    assert h.get("host") == "example.com:8080"
    assert h.get("date") == "Tue, 15 Nov 1994 08:12:31 GMT"
    assert h.get("x") == "a:b:c:"


def test_the_split_is_at_the_first_colon():
    assert parse_headers("A::b").items() == [("A", ":b")]
    assert parse_headers("A: :").items() == [("A", ":")]


def test_name_spelling_is_kept():
    h = parse_headers("content-TYPE: text/html\r\nX-API-Key: k")
    assert [name for name, _ in h.items()] == ["content-TYPE", "X-API-Key"]


@pytest.mark.parametrize(
    "name",
    [
        "A",
        "x-y",
        "X_Y",
        "a.b",
        "a!b",
        "a#b",
        "a$b",
        "a%b",
        "a&b",
        "a'b",
        "a*b",
        "a+b",
        "a^b",
        "a`b",
        "a|b",
        "a~b",
        "123",
        "9a",
    ],
)
def test_every_token_character_is_allowed_in_a_name(name):
    assert parse_headers(f"{name}: v").items() == [(name, "v")]


def test_empty_text_and_empty_values_are_fine():
    assert parse_headers("").items() == []
    assert len(parse_headers("")) == 0
    h = parse_headers("A:\r\nB: x")
    assert h.get("A") == ""
    assert h.items() == [("A", ""), ("B", "x")]


def test_items_returns_a_new_list_each_time():
    h = parse_headers("A: 1")
    first = h.items()
    first.append(("Z", "9"))
    first.clear()
    assert h.items() == [("A", "1")]
    assert len(h) == 1
