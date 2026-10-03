import pytest
from wordwrap import wrap


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("the quick brown fox jumps", 10, ["the quick", "brown fox", "jumps"]),
        ("aaa bbb ccc", 7, ["aaa bbb", "ccc"]),
        ("aaa bbb ccc", 11, ["aaa bbb ccc"]),
        ("aaa bbb ccc", 100, ["aaa bbb ccc"]),
        ("aaa bbb ccc", 6, ["aaa", "bbb", "ccc"]),
        ("one", 3, ["one"]),
        ("a b c d e f", 3, ["a b", "c d", "e f"]),
        ("a b c d e f", 1, ["a", "b", "c", "d", "e", "f"]),
    ],
)
def test_greedy_filling(text, width, expected):
    assert wrap(text, width) == expected


def test_a_line_may_be_exactly_width_long_but_not_longer():
    assert wrap("abcd efgh ij", 9) == ["abcd efgh", "ij"]
    assert wrap("abcd efgh ij", 8) == ["abcd", "efgh ij"]


def test_greedy_not_balanced():
    # A balanced wrap would give "aa bb" / "cc dd" / "ee"; greedy packs the first line fullest.
    assert wrap("aa bb cc dd ee", 8) == ["aa bb cc", "dd ee"]


def test_a_short_word_after_a_long_line_still_goes_to_the_next_line():
    assert wrap("abcdefgh i j", 8) == ["abcdefgh", "i j"]


def test_the_result_is_a_list_of_str():
    result = wrap("a b c", 3)
    assert type(result) is list and all(type(line) is str for line in result)
