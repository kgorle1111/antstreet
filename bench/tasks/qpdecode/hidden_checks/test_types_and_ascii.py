import pytest
from qpdecode import decode


@pytest.mark.parametrize(
    "text",
    ["caf\u00e9", "\u00e9", "a\u2022b", "\u4e2d", "=41\u00e9", "abc\x80", "\U0001f600", "\xff"],
)
def test_a_character_beyond_ascii_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize("text", [b"abc", None, 5, ["a"], bytearray(b"a"), 1.5])
def test_a_text_that_is_not_a_str_raises_type_error(text):
    with pytest.raises(TypeError):
        decode(text)


def test_the_last_ascii_character_and_control_characters_pass_through():
    assert decode("\x7f") == b"\x7f"
    assert decode("a\x01b") == b"a\x01b"
    assert decode("\x00") == b"\x00"


def test_non_ascii_text_is_refused_even_when_it_would_otherwise_be_a_soft_break_or_whitespace():
    with pytest.raises(ValueError):
        decode("abc=\r\ndef\u00e9")
    with pytest.raises(ValueError):
        decode("abc  \u00a0")
