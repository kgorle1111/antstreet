import pytest
from cobs import decode


def test_empty_input_raises_value_error():
    with pytest.raises(ValueError):
        decode(b"")
    with pytest.raises(ValueError):
        decode(bytearray())


@pytest.mark.parametrize(
    "data",
    [
        b"\x00",
        b"\x00\x01",
        b"\x01\x00",
        b"\x01\x01\x00",
        b"\x03\x11\x00",
        b"\x03\x11\x22\x00",  # the packet delimiter is not part of the data
        b"\x03\x11\x22\x00\x02\x33",
        b"\x02\x00",
        b"\x01\x02\x11\x01\x00",
        b"\xff" + bytes(range(1, 255)) + b"\x00",
        b"\x00" * 5,
    ],
)
def test_a_zero_byte_anywhere_raises_value_error(data):
    with pytest.raises(ValueError):
        decode(data)


@pytest.mark.parametrize(
    "data",
    [
        b"\x02",
        b"\x05\x11\x22",
        b"\x03\x11",
        b"\xff",
        b"\xff\x01\x02\x03",
        b"\x02\x11\x03\x22",
        b"\x01\x02\x11\x05",
        b"\x01\x01\x02",
        b"\x02a\x02b\x03c",
    ],
)
def test_a_last_block_that_promises_more_bytes_than_are_left_raises_value_error(data):
    with pytest.raises(ValueError):
        decode(data)


def test_one_byte_short_of_a_full_block_raises_value_error():
    full = b"\xff" + bytes(range(1, 255))
    assert len(full) == 255
    assert decode(full) == bytes(range(1, 255))
    with pytest.raises(ValueError):
        decode(full[:-1])
    with pytest.raises(ValueError):
        decode(full[:1])


def test_cutting_a_valid_encoding_one_byte_short_raises_value_error_unless_it_ends_on_a_block():
    encoded = b"\x04abc\x03de"
    assert decode(encoded) == b"abc\x00de"
    with pytest.raises(ValueError):
        decode(encoded[:-1])
    assert decode(encoded[:4]) == b"abc"  # cut exactly after the first block
    with pytest.raises(ValueError):
        decode(encoded[:3])


def test_an_error_late_in_a_long_input_still_raises():
    good = b"\x02a" * 500
    assert decode(good) == b"\x00".join([b"a"] * 500)
    with pytest.raises(ValueError):
        decode(good + b"\x05")
    with pytest.raises(ValueError):
        decode(good[:300] + b"\x00" + good[300:])
