import pytest
from editdistance import edit_distance


@pytest.mark.parametrize(
    ("a", "b", "d"),
    [
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("saturday", "sunday", 3),
        ("intention", "execution", 5),
        ("", "abc", 3),
        ("abc", "", 3),
        ("abc", "abc", 0),
        ("a", "b", 1),
        ("ab", "ba", 2),
        ("abc", "ac", 1),
        ("abcdef", "azced", 3),
        ("gumbo", "gambol", 2),
        ("aaaa", "aa", 2),
    ],
)
def test_known_distances(a, b, d):
    assert edit_distance(a, b) == d
    assert edit_distance(b, a) == d


def test_a_result_is_a_plain_int():
    assert type(edit_distance("a", "b")) is int
