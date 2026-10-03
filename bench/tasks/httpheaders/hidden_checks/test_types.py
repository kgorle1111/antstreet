import pytest
from httpheaders import Headers, parse_headers


@pytest.mark.parametrize("text", [b"A: 1", None, 5, ["A: 1"], bytearray(b"A: 1"), 1.5, ("A: 1",)])
def test_a_text_that_is_not_a_str_raises_type_error(text):
    with pytest.raises(TypeError):
        parse_headers(text)


def test_parse_headers_returns_a_headers_object():
    h = parse_headers("A: 1")
    assert isinstance(h, Headers)
    assert type(len(h)) is int


def test_get_returns_str_or_the_default_and_get_all_a_list_of_str():
    h = parse_headers("A: 1\r\nA: 2")
    assert type(h.get("a")) is str
    assert all(type(v) is str for v in h.get_all("a"))
    assert all(type(n) is str and type(v) is str for n, v in h.items())
    assert all(type(pair) is tuple for pair in h.items())
    sentinel = object()
    assert h.get("zzz", sentinel) is sentinel


def test_in_is_false_for_anything_that_is_not_a_str():
    h = parse_headers("1: x\r\nA: 1")
    assert 1 not in h
    assert b"A" not in h
    assert ("A", "1") not in h
    assert None not in h
    assert "1" in h


def test_a_realistic_request_block():
    text = (
        "Host: example.org\r\n"
        "User-Agent: probe/1.0\r\n"
        "Accept: text/html\r\n"
        "Accept: application/json;q=0.9\r\n"
        "X-Long: part one,\r\n"
        "  part two\r\n"
        "cookie: a=1\r\n"
        "Cookie: b=2\r\n"
        "\r\n"
        "ignored: body\r\n"
    )
    h = parse_headers(text)
    assert len(h) == 7
    assert h.get("accept") == "text/html, application/json;q=0.9"
    assert h.get("X-LONG") == "part one, part two"
    assert h.get_all("COOKIE") == ["a=1", "b=2"]
    assert h.get("ignored") is None
    assert [n for n, _ in h.items()][:3] == ["Host", "User-Agent", "Accept"]
