import pytest
from qpdecode import decode


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("", b""),
        ("hello world", b"hello world"),
        ("caf=C3=A9", b"caf\xc3\xa9"),
        ("caf=c3=a9", b"caf\xc3\xa9"),
        ("caf=C3=a9", b"caf\xc3\xa9"),
        ("=3D", b"="),
        ("=3d", b"="),
        ("a=3Db", b"a=b"),
        ("=3D=3D", b"=="),
        ("=41=42=43", b"ABC"),
        ("=00", b"\x00"),
        ("=FF", b"\xff"),
        ("=ff", b"\xff"),
        ("=0D=0A", b"\r\n"),
        ("=0a=0D", b"\n\r"),
        ("x=7Ey", b"x~y"),
    ],
)
def test_known_decodings(text, raw):
    assert decode(text) == raw


def test_every_byte_value_has_an_escape_in_both_cases():
    for n in range(256):
        assert decode(f"={n:02X}") == bytes([n])
        assert decode(f"={n:02x}") == bytes([n])


def test_the_result_is_bytes():
    assert type(decode("abc")) is bytes
    assert type(decode("")) is bytes
    assert type(decode("=C3")) is bytes


def test_an_escape_is_three_characters_and_does_not_swallow_neighbours():
    assert decode("=41B") == b"AB"
    assert decode("=414") == b"A4"
    assert decode("=4141") == b"A41"
    assert decode("A=41A") == b"AAA"
    assert decode("=3D41") == b"=41"


def test_an_escape_for_a_line_break_is_just_bytes_not_a_line_break():
    # the two bytes CR LF came from the escapes, so no whitespace stripping or line logic applies
    assert decode("a=20=0D=0Ab") == b"a \r\nb"
    assert decode("a=0D=0A  \nb") == b"a\r\n\nb"


def test_other_ascii_characters_stand_for_themselves():
    text = "".join(chr(c) for c in range(33, 127) if chr(c) != "=")
    assert decode(text) == text.encode("ascii")
    assert decode("a b\tc") == b"a b\tc"
