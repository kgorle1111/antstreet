import pytest
from httpheaders import parse_headers

TEXT = "Content-Type: text/html\r\nX-Request-ID: abc\r\n"


@pytest.mark.parametrize("name", ["Content-Type", "content-type", "CONTENT-TYPE", "cOnTeNt-tYpE"])
def test_get_ignores_the_case_of_the_name(name):
    assert parse_headers(TEXT).get(name) == "text/html"


@pytest.mark.parametrize("name", ["X-Request-ID", "x-request-id", "X-REQUEST-id"])
def test_get_all_ignores_the_case_of_the_name(name):
    assert parse_headers(TEXT).get_all(name) == ["abc"]


@pytest.mark.parametrize("name", ["Content-Type", "content-type", "CONTENT-TYPE"])
def test_in_ignores_the_case_of_the_name(name):
    assert name in parse_headers(TEXT)


def test_the_stored_spelling_does_not_decide_the_lookup():
    h = parse_headers("ACCEPT: a\r\naccept: b\r\nAccept: c")
    for spelling in ("accept", "Accept", "ACCEPT"):
        assert h.get_all(spelling) == ["a", "b", "c"]
    assert [n for n, _ in h.items()] == ["ACCEPT", "accept", "Accept"]


def test_only_ascii_letters_are_folded():
    h = parse_headers("key: v")
    assert h.get("\u212aey") is None  # KELVIN SIGN, whose lower() is "k"
    assert h.get_all("\u212aey") == []
    assert "\u212aey" not in h
    assert "KEY" in h
    h2 = parse_headers("A: 1")
    assert "\uff21" not in h2  # FULLWIDTH A
    assert h2.get("\uff41") is None


def test_different_names_are_different_headers():
    h = parse_headers("A: 1\r\nAB: 2\r\nB: 3")
    assert h.get("a") == "1"
    assert h.get("ab") == "2"
    assert h.get("abc") is None
    assert "A B" not in h
    assert "" not in h


def test_digits_and_punctuation_in_names_compare_exactly():
    h = parse_headers("X-1: a\r\nx_1: b")
    assert h.get("x-1") == "a"
    assert h.get("X_1") == "b"
    assert h.get("x1") is None
