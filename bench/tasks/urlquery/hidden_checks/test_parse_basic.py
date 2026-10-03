import pytest
from urlquery import parse_query


@pytest.mark.parametrize(
    ("qs", "expected"),
    [
        ("a=1", {"a": ["1"]}),
        ("a=1&b=2", {"a": ["1"], "b": ["2"]}),
        ("name=Ada+Lovelace&lang=en", {"name": ["Ada Lovelace"], "lang": ["en"]}),
        ("a=1=2", {"a": ["1=2"]}),
        ("a==", {"a": ["="]}),
        ("a=", {"a": [""]}),
        ("flag", {"flag": [""]}),
        ("flag&x=1", {"flag": [""], "x": ["1"]}),
        ("a=b=c&d=e", {"a": ["b=c"], "d": ["e"]}),
    ],
)
def test_pairs_split_at_the_first_equals(qs, expected):
    assert parse_query(qs) == expected


@pytest.mark.parametrize("qs", ["", "?", "&", "&&&", "?&", "="])
def test_nothing_in_gives_an_empty_dict(qs):
    assert parse_query(qs) == {}


@pytest.mark.parametrize(
    ("qs", "expected"),
    [
        ("?a=1", {"a": ["1"]}),
        ("??a=1", {"?a": ["1"]}),
        ("a=1&&b=2", {"a": ["1"], "b": ["2"]}),
        ("&a=1&", {"a": ["1"]}),
        ("=x&a=1", {"a": ["1"]}),
        ("=&a=1&=y=z", {"a": ["1"]}),
    ],
)
def test_leading_question_mark_empty_segments_and_empty_keys(qs, expected):
    assert parse_query(qs) == expected


def test_the_result_is_a_dict_of_lists():
    result = parse_query("a=1&a=2")
    assert isinstance(result, dict) and isinstance(result["a"], list)
