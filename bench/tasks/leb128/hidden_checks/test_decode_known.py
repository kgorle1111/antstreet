import pytest
from leb128 import decode_signed, decode_unsigned


@pytest.mark.parametrize(
    ("encoded", "value"),
    [
        ("00", 0),
        ("01", 1),
        ("7f", 127),
        ("8001", 128),
        ("8101", 129),
        ("ff01", 255),
        ("8002", 256),
        ("ff7f", 16383),
        ("808001", 16384),
        ("e58e26", 624485),
        ("ffffffff0f", 2**32 - 1),
        ("80808080808080808001", 2**63),
        ("ffffffffffffffffff01", 2**64 - 1),
    ],
)
def test_unsigned_vectors(encoded, value):
    data = bytes.fromhex(encoded)
    assert decode_unsigned(data) == (value, len(data))


@pytest.mark.parametrize(
    ("encoded", "value"),
    [
        ("00", 0),
        ("01", 1),
        ("7f", -1),
        ("02", 2),
        ("7e", -2),
        ("3f", 63),
        ("c000", 64),
        ("40", -64),
        ("bf7f", -65),
        ("ff00", 127),
        ("817f", -127),
        ("8001", 128),
        ("807f", -128),
        ("ff7e", -129),
        ("c0bb78", -123456),
        ("ffffffffffffffffff00", 2**63 - 1),
        ("8080808080808080807f", -(2**63)),
    ],
)
def test_signed_vectors(encoded, value):
    data = bytes.fromhex(encoded)
    assert decode_signed(data) == (value, len(data))


def test_the_same_bytes_read_differently_as_unsigned_and_signed():
    assert decode_unsigned(b"\x7f") == (127, 1)
    assert decode_signed(b"\x7f") == (-1, 1)
    assert decode_unsigned(b"\x40") == (64, 1)
    assert decode_signed(b"\x40") == (-64, 1)
    assert decode_unsigned(b"\xc0\x00") == (64, 2)
    assert decode_signed(b"\xc0\x00") == (64, 2)


def test_the_result_is_a_tuple_of_two_ints():
    for func in (decode_unsigned, decode_signed):
        result = func(b"\x05")
        assert type(result) is tuple and len(result) == 2
        assert type(result[0]) is int and type(result[1]) is int


def test_a_bytearray_is_accepted():
    assert decode_unsigned(bytearray(b"\x80\x01")) == (128, 2)
    assert decode_signed(bytearray(b"\x7f")) == (-1, 1)
