import pytest
from wordwrap import wrap


def test_the_example_from_the_description():
    assert wrap("abcdefghijkl x", 5) == ["abcde", "fghij", "kl x"]


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("abcdefgh", 4, ["abcd", "efgh"]),
        ("abcdefghi", 4, ["abcd", "efgh", "i"]),
        ("abcdefghij", 3, ["abc", "def", "ghi", "j"]),
        ("abcde", 5, ["abcde"]),
        ("abcdef", 5, ["abcde", "f"]),
        ("abc", 1, ["a", "b", "c"]),
    ],
)
def test_a_single_long_word_is_cut_into_pieces(text, width, expected):
    assert wrap(text, width) == expected


def test_the_open_line_is_finished_before_a_long_word_is_cut():
    # "ab" is not topped up with the first piece of the long word.
    assert wrap("ab cdefghijk", 6) == ["ab", "cdefgh", "ijk"]


def test_words_may_follow_the_last_piece():
    assert wrap("abcdefgh ij kl", 6) == ["abcdef", "gh ij", "kl"]


def test_the_last_piece_can_start_a_line_that_is_then_full():
    assert wrap("abcdefghij kl", 5) == ["abcde", "fghij", "kl"]


def test_two_long_words_in_a_row():
    assert wrap("abcdefg hijklmn", 4) == ["abcd", "efg", "hijk", "lmn"]


def test_a_word_that_exactly_fills_the_line_is_not_cut():
    assert wrap("ab abcdef gh", 6) == ["ab", "abcdef", "gh"]


def test_long_word_with_indents_uses_the_room_after_each_indent():
    # First line has room 4 after "> ", later lines have room 5 after "  ".
    assert wrap("abcdefghijklm", 6, first_indent="> ", rest_indent=" ") == [
        "> abcd",
        " efghi",
        " jklm",
    ]


def test_long_word_in_the_middle_of_a_paragraph():
    assert wrap("see https://example.com/very/long/path now", 12) == [
        "see",
        "https://exam",
        "ple.com/very",
        "/long/path",
        "now",
    ]
