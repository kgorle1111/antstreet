import pytest
from leb128 import decode_signed, decode_unsigned


def test_bytes_after_the_number_are_not_read():
    assert decode_unsigned(b"\x80\x01\xff") == (128, 2)
    assert decode_unsigned(b"\x05\x80") == (5, 1)
    assert decode_signed(b"\x7f\xff\xff") == (-1, 1)
    assert decode_signed(b"\xc0\x00\x80") == (64, 2)


def test_decoding_starts_at_the_offset_and_returns_the_next_offset():
    assert decode_unsigned(b"\xaa\x05\x07", 1) == (5, 2)
    assert decode_unsigned(b"\xaa\x05\x07", 2) == (7, 3)
    assert decode_unsigned(b"\xaa\xe5\x8e\x26\x00", 1) == (624485, 4)
    assert decode_signed(b"\xaa\x7f\x07", 1) == (-1, 2)
    assert decode_signed(b"\x00\x00\xc0\xbb\x78", 2) == (-123456, 5)


def test_a_stream_of_numbers_is_read_one_after_another():
    data = b"".join([b"\x01", b"\x80\x01", b"\xe5\x8e\x26", b"\x00", b"\xff\xff\xff\xff\x0f"])
    values = []
    offset = 0
    while offset < len(data):
        value, offset = decode_unsigned(data, offset)
        values.append(value)
    assert values == [1, 128, 624485, 0, 2**32 - 1]
    assert offset == len(data)


def test_a_stream_of_signed_numbers():
    data = bytes.fromhex("7fc00040c0bb7800")
    out = []
    offset = 0
    while offset < len(data):
        value, offset = decode_signed(data, offset)
        out.append(value)
    assert out == [-1, 64, -64, -123456, 0]


@pytest.mark.parametrize("offset", [-1, -100, 4, 5, 100])
def test_an_offset_outside_the_data_raises_value_error(offset):
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(ValueError):
            func(b"\x01\x02\x03", offset)


def test_an_offset_at_the_end_raises_value_error_because_no_number_is_there():
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(ValueError):
            func(b"\x01\x02\x03", 3)
        with pytest.raises(ValueError):
            func(b"", 0)


@pytest.mark.parametrize("offset", ["0", None, 1.0, True, b"\x00", [0]])
def test_an_offset_that_is_not_an_int_raises_type_error(offset):
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(TypeError):
            func(b"\x01\x02", offset)


@pytest.mark.parametrize("data", ["\x01", None, 1, [1], (1,), 1.5, memoryview(b"\x01")])
def test_data_that_is_not_bytes_or_bytearray_raises_type_error(data):
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(TypeError):
            func(data)
