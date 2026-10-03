import pytest
from urlquery import parse_query


@pytest.mark.parametrize(
    "qs", ["a=%", "a=%4", "a=%zz", "a=%4g", "a=%g4", "a=100%", "a=%-1", "a=% 1", "%=1", "%2=1"]
)
def test_bad_percent_escape_raises(qs):
    with pytest.raises(ValueError):
        parse_query(qs)


@pytest.mark.parametrize("qs", ["a=%FF", "a=%C3", "a=%C3%28", "a=%80", "a=%E2%82", "%FF=1"])
def test_invalid_utf8_raises(qs):
    with pytest.raises(ValueError):
        parse_query(qs)


def test_an_error_in_a_later_segment_raises():
    with pytest.raises(ValueError):
        parse_query("a=1&b=2&c=%zz")


@pytest.mark.parametrize("bad", [None, 1, b"a=1", ["a=1"], {"a": "1"}, 2.5])
def test_non_string_argument_raises_value_error(bad):
    with pytest.raises(ValueError):
        parse_query(bad)
