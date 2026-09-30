from justify import justify


def test_classic_example():
    text = "This is an example of text justification."
    assert justify(text, 16) == ["This    is    an", "example  of text", "justification.  "]


def test_extra_spaces_divide_evenly():
    # 10 letters, 2 gaps, 6 spaces: 3 per gap.
    assert justify("aaaa bbbb cc ddddddd", 16) == ["aaaa   bbbb   cc", "ddddddd         "]


def test_leftmost_gaps_get_the_remainder():
    # 6 letters, 2 gaps, 5 spaces: 3 then 2.
    assert justify("ab cd ef ghij", 11) == ["ab   cd  ef", "ghij       "]
    # 4 letters, 3 gaps, 5 spaces: 2, 2, 1.
    assert justify("a b c d eeeeeeee", 9) == ["a  b  c d", "eeeeeeee "]


def test_a_single_extra_space_goes_to_the_first_gap():
    # 5 letters, 4 gaps, 5 spaces: 2, 1, 1, 1.
    assert justify("a b c d e ffffffff", 10) == ["a  b c d e", "ffffffff  "]


def test_two_words_are_pushed_to_the_edges():
    assert justify("ab cd efghijkl", 10) == ["ab      cd", "efghijkl  "]
