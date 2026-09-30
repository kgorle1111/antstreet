import pytest
from justify import justify


@pytest.mark.parametrize("width", [0, -1, -20])
def test_width_below_one_raises(width):
    with pytest.raises(ValueError):
        justify("hello world", width)


@pytest.mark.parametrize("text", ["", "   "])
def test_width_below_one_raises_even_for_empty_text(text):
    with pytest.raises(ValueError):
        justify(text, 0)


def test_word_longer_than_width_raises():
    with pytest.raises(ValueError):
        justify("abcdef", 5)


def test_long_word_raises_wherever_it_appears():
    with pytest.raises(ValueError):
        justify("ab abcdef", 5)
    with pytest.raises(ValueError):
        justify("ab cd ef gh ij klmnopqrstuvwxyz", 12)


def test_word_exactly_width_long_is_fine():
    assert justify("abcde", 5) == ["abcde"]
    assert justify("abcde fghij", 5) == ["abcde", "fghij"]
