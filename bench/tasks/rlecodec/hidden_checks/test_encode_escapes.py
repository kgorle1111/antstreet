import pytest
from rlecodec import decode, encode


@pytest.mark.parametrize(
    ("text", "encoded"),
    [
        ("1", "1\\1"),
        ("11", "2\\1"),
        ("0", "1\\0"),
        ("9", "1\\9"),
        ("111222", "3\\13\\2"),
        ("a1", "1a1\\1"),
        ("1a", "1\\11a"),
        ("1" * 12, "12\\1"),
        ("007", "2\\01\\7"),
        ("2024", "1\\21\\01\\21\\4"),
        ("\\", "1\\\\"),
        ("\\\\", "2\\\\"),
        ("\\\\\\", "3\\\\"),
        ("a\\b", "1a1\\\\1b"),
        ("\\1", "1\\\\1\\1"),
        ("1\\", "1\\11\\\\"),
        ("\\\\11", "2\\\\2\\1"),
    ],
)
def test_digits_and_backslashes_are_escaped(text, encoded):
    assert encode(text) == encoded
    assert decode(encoded) == text


def test_every_ascii_digit_is_escaped():
    for d in "0123456789":
        assert encode(d) == "1\\" + d
        assert encode(d * 3) == "3\\" + d


def test_no_other_ascii_character_is_escaped():
    for code in range(0, 128):
        ch = chr(code)
        if ch.isdigit() or ch == "\\":
            continue
        assert encode(ch) == "1" + ch
        assert encode(ch * 5) == "5" + ch


def test_the_count_of_an_escaped_run_is_written_before_the_backslash():
    assert encode("5" * 7) == "7\\5"
    assert encode("\\" * 7) == "7\\\\"


def test_a_mixed_text():
    text = "a1b22c333\\d4444"
    assert encode(text) == "1a1\\11b2\\21c3\\31\\\\1d4\\4"
    assert decode(encode(text)) == text
