from justify import justify


def test_single_word_line_before_the_last_is_left_aligned():
    assert justify("aaaaaa bbbbbbbb c", 8) == ["aaaaaa  ", "bbbbbbbb", "c       "]


def test_single_word_text():
    assert justify("hi", 5) == ["hi   "]
    assert justify("hello", 5) == ["hello"]


def test_several_single_word_lines_in_a_row():
    assert justify("abcdefg hij klmnopq", 8) == ["abcdefg ", "hij     ", "klmnopq "]
