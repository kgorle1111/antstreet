import pytest
from qpdecode import decode


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("abc=\r\ndef", b"abcdef"),
        ("abc=\ndef", b"abcdef"),
        ("abc=", b"abc"),
        ("abc=\r\n", b"abc"),
        ("abc=\n", b"abc"),
        ("a=\r\nb=\r\nc=\r\nd", b"abcd"),
        ("a=\nb=\nc", b"abc"),
        ("a=\r\nb=\nc=", b"abc"),
        ("=\r\n", b""),
        ("=\n", b""),
        ("=", b""),
        ("=\r\n=\r\n=", b""),
    ],
)
def test_soft_line_breaks_join_the_lines(text, raw):
    assert decode(text) == raw


def test_a_soft_break_after_an_escape():
    assert decode("caf=C3=\r\n=A9") == b"caf\xc3\xa9"
    assert decode("=3D=\nx") == b"=x"


def test_the_line_after_a_soft_break_is_still_a_line():
    assert decode("abc=\r\ndef\r\nghi") == b"abcdef\r\nghi"
    assert decode("abc=\ndef\nghi") == b"abcdef\nghi"


def test_a_soft_break_followed_by_a_hard_one():
    assert decode("abc=\r\n\r\ndef") == b"abc\r\ndef"
    assert decode("abc=\n\ndef") == b"abc\ndef"


def test_an_escaped_equals_sign_at_the_end_is_not_a_soft_break():
    assert decode("abc=3D") == b"abc="
    assert decode("abc=3D\r\ndef") == b"abc=\r\ndef"


def test_a_long_message_wrapped_into_short_lines():
    body = b"The quick brown fox jumps over the lazy dog. " * 8
    pieces = [body.decode()[i : i + 60].replace(" ", "=20") for i in range(0, len(body), 60)]
    assert decode("=\r\n".join(pieces)) == body
    assert decode("=\n".join(pieces)) == body
