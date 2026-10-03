import pytest
from cobs import encode


@pytest.mark.parametrize(
    ("data", "encoded"),
    [
        (b"", b"\x01"),
        (b"\x00", b"\x01\x01"),
        (b"\x00\x00", b"\x01\x01\x01"),
        (b"\x00\x00\x00", b"\x01\x01\x01\x01"),
        (b"\x00\x11\x00", b"\x01\x02\x11\x01"),
        (b"\x11\x22\x00\x33", b"\x03\x11\x22\x02\x33"),
        (b"\x11\x22\x33\x44", b"\x05\x11\x22\x33\x44"),
        (b"\x11\x00\x00\x00", b"\x02\x11\x01\x01\x01"),
        (b"\x11", b"\x02\x11"),
        (b"\x11\x00", b"\x02\x11\x01"),
        (b"\x00\x11", b"\x01\x02\x11"),
        (b"\x01\x02\x03\x00\x04", b"\x04\x01\x02\x03\x02\x04"),
        (b"\xff", b"\x02\xff"),
        (b"\xff\x00\xff", b"\x02\xff\x02\xff"),
        (b"abc", b"\x04abc"),
        (b"Hello\x00World", b"\x06Hello\x06World"),
        (b"\x00" * 10, b"\x01" * 11),
    ],
)
def test_known_encodings(data, encoded):
    assert encode(data) == encoded


def test_a_bytearray_gives_the_same_result():
    assert encode(bytearray(b"\x11\x22\x00\x33")) == b"\x03\x11\x22\x02\x33"
    assert encode(bytearray()) == b"\x01"


def test_the_result_is_bytes():
    assert type(encode(b"")) is bytes
    assert type(encode(b"\x00abc")) is bytes


def test_the_code_byte_is_the_distance_to_the_next_zero_plus_one():
    assert encode(b"a\x00") == b"\x02a\x01"
    assert encode(b"ab\x00") == b"\x03ab\x01"
    assert encode(b"abc\x00") == b"\x04abc\x01"
    assert encode(b"abc\x00de") == b"\x04abc\x03de"
    assert encode(b"abc\x00\x00de") == b"\x04abc\x01\x03de"


def test_the_input_is_not_changed():
    data = bytearray(b"\x00\x01\x00")
    encode(data)
    assert data == bytearray(b"\x00\x01\x00")
