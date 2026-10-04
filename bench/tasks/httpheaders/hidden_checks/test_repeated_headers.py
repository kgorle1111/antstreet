from httpheaders import parse_headers


def test_repeated_headers_are_separate_entries_in_order():
    h = parse_headers("Accept: a\r\nHost: h\r\nAccept: b\r\nAccept: c\r\n")
    assert h.items() == [("Accept", "a"), ("Host", "h"), ("Accept", "b"), ("Accept", "c")]
    assert len(h) == 4


def test_get_all_lists_every_value_in_text_order():
    h = parse_headers("Accept: a\r\nHost: h\r\nAccept: b\r\nAccept: c\r\n")
    assert h.get_all("accept") == ["a", "b", "c"]
    assert h.get_all("host") == ["h"]
    assert type(h.get_all("accept")) is list


def test_get_joins_the_values_with_comma_and_space():
    h = parse_headers("Accept: a\r\nHost: h\r\nAccept: b\r\nAccept: c\r\n")
    assert h.get("Accept") == "a, b, c"
    assert h.get("Host") == "h"


def test_a_single_value_is_returned_as_it_is():
    assert parse_headers("A: x, y").get("a") == "x, y"
    assert parse_headers("A: ").get("a") == ""


def test_values_that_already_hold_commas_are_joined_again():
    h = parse_headers("A: 1, 2\r\nA: 3")
    assert h.get("a") == "1, 2, 3"
    assert h.get_all("a") == ["1, 2", "3"]


def test_repeated_names_in_different_case_are_one_name():
    h = parse_headers("Via: 1.0 a\r\nvia: 1.1 b\r\nVIA: 1.1 c")
    assert h.get("via") == "1.0 a, 1.1 b, 1.1 c"
    assert h.get_all("Via") == ["1.0 a", "1.1 b", "1.1 c"]


def test_the_default_is_used_only_when_the_name_is_absent():
    h = parse_headers("A: 1\r\nE:")
    assert h.get("missing") is None
    assert h.get("missing", "fallback") == "fallback"
    assert h.get("missing", default="d") == "d"
    assert h.get("a", "fallback") == "1"
    assert h.get("e", "fallback") == ""
    assert h.get_all("missing") == []


def test_in_and_len_with_repeats():
    h = parse_headers("A: 1\r\nA: 2\r\nB: 3")
    assert "a" in h and "B" in h and "c" not in h
    assert len(h) == 3
    assert 5 not in h
    assert None not in h
    assert b"A" not in h
