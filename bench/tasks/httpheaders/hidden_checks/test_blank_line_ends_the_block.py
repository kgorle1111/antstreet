import pytest
from httpheaders import parse_headers


def test_text_after_the_empty_line_is_ignored():
    h = parse_headers("A: 1\r\nB: 2\r\n\r\nthis is a body")
    assert h.items() == [("A", "1"), ("B", "2")]
    assert "this is a body" not in h


@pytest.mark.parametrize(
    "text",
    [
        "A: 1\n\nnot a header",
        "A: 1\r\n\r\nnot a header",
        "A: 1\r\n\r\n: broken",
        "A: 1\r\n\r\n  folded body",
        "A: 1\r\n\r\nB: 2",
        "A: 1\n\n\n\nB: 2",
        "A: 1\r\n\r\n\r\nB: 2\r\n",
        "A: 1\n\r\n:::",
    ],
)
def test_nothing_after_the_empty_line_is_read(text):
    assert parse_headers(text).items() == [("A", "1")]


@pytest.mark.parametrize("text", ["\r\nA: 1", "\nA: 1", "\r\n", "\n", "\n\n", "\r\n\r\nA: 1"])
def test_a_block_that_starts_with_an_empty_line_has_no_headers(text):
    h = parse_headers(text)
    assert h.items() == []
    assert len(h) == 0
    assert "A" not in h
    assert h.get("A") is None


def test_a_line_of_only_spaces_after_a_header_is_not_an_empty_line():
    h = parse_headers("A: 1\r\n   \r\nB: 2")
    assert h.items() == [("A", "1"), ("B", "2")]


def test_a_missing_final_line_ending_is_fine():
    assert parse_headers("A: 1").items() == [("A", "1")]
    assert parse_headers("A: 1\r\nB: 2").items() == [("A", "1"), ("B", "2")]
