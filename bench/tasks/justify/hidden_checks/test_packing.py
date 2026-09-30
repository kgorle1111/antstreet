from justify import justify


def _words(lines):
    return [line.split() for line in lines]


def test_greedy_line_breaks():
    lines = justify("This is an example of text justification.", 16)
    assert _words(lines) == [["This", "is", "an"], ["example", "of", "text"], ["justification."]]


def test_a_word_goes_on_the_line_when_it_fits_exactly():
    # "aaa bbb" is 7 characters: exactly width, so both words share a line.
    assert _words(justify("aaa bbb ccc", 7)) == [["aaa", "bbb"], ["ccc"]]
    # One character short of fitting: "bbb" must wrap.
    assert _words(justify("aaa bbb ccc", 6)) == [["aaa"], ["bbb"], ["ccc"]]


def test_width_one_puts_each_letter_on_its_own_line():
    assert justify("a b c", 1) == ["a", "b", "c"]


def test_words_are_never_reordered_or_altered():
    text = "The quick brown fox jumps over the lazy dog"
    lines = justify(text, 12)
    assert [w for line in lines for w in line.split()] == text.split()
