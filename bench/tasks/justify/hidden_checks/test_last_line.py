from justify import justify


def test_last_line_is_left_aligned_with_single_spaces():
    lines = justify("one two three four five six seven", 20)
    assert lines == ["one  two  three four", "five six seven      "]


def test_text_that_fits_on_one_line_is_not_stretched():
    assert justify("hello there world", 30) == ["hello there world" + " " * 13]


def test_last_line_with_one_word_is_padded():
    assert justify("ab cd efghijkl", 10)[-1] == "efghijkl  "


def test_last_line_filling_the_width_exactly():
    assert justify("a b c", 5) == ["a b c"]
