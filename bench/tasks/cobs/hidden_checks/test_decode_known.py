import pytest
from cobs import decode


@pytest.mark.parametrize(
    ("encoded", "data"),
    [
        (b"\x01", b""),
        (b"\x01\x01", b"\x00"),
        (b"\x01\x01\x01", b"\x00\x00"),
        (b"\x01\x01\x01\x01", b"\x00\x00\x00"),
        (b"\x01\x02\x11\x01", b"\x00\x11\x00"),
        (b"\x03\x11\x22\x02\x33", b"\x11\x22\x00\x33"),
        (b"\x05\x11\x22\x33\x44", b"\x11\x22\x33\x44"),
        (b"\x02\x11\x01\x01\x01", b"\x11\x00\x00\x00"),
        (b"\x02\x11", b"\x11"),
        (b"\x02\x11\x01", b"\x11\x00"),
        (b"\x01\x02\x11", b"\x00\x11"),
        (b"\x04\x01\x02\x03\x02\x04", b"\x01\x02\x03\x00\x04"),
        (b"\x06Hello\x06World", b"Hello\x00World"),
    ],
)
def test_known_decodings(encoded, data):
    assert decode(encoded) == data


def test_a_full_block_implies_no_zero():
    data = bytes(range(1, 255))
    assert decode(b"\xff" + data) == data
    assert decode(b"\xff" + data + b"\xff" + data) == data + data
    assert decode(b"\xff" + data + b"\x02\xff") == data + b"\xff"


def test_a_zero_is_written_after_a_short_block_only_when_more_blocks_follow():
    assert decode(b"\x02a") == b"a"
    assert decode(b"\x02a\x02b") == b"a\x00b"
    assert decode(b"\x02a\x02b\x02c") == b"a\x00b\x00c"
    assert decode(b"\x02a\x01") == b"a\x00"


def test_blocks_the_encoder_would_not_write_are_still_read():
    data = bytes(range(1, 255))
    assert decode(b"\xff" + data + b"\x01") == data  # an empty block after a full one
    assert decode(b"\xff" + data + b"\x01\x01") == data + b"\x00"
    assert decode(b"\x03\x11\x22") == b"\x11\x22"  # no zero follows the last block
    assert decode(b"\x01\x01\x01\x01\x01") == b"\x00" * 4


def test_a_bytearray_is_accepted_and_the_result_is_bytes():
    assert decode(bytearray(b"\x03\x11\x22\x02\x33")) == b"\x11\x22\x00\x33"
    assert type(decode(b"\x01")) is bytes
    assert type(decode(b"\x02a\x02b")) is bytes


def test_a_code_of_ff_in_the_middle_of_a_run_of_blocks():
    first = bytes(range(1, 255))
    second = bytes(range(10, 20))
    encoded = b"\xff" + first + bytes([len(second) + 1]) + second + b"\x03xy"
    assert decode(encoded) == first + second + b"\x00" + b"xy"


def test_the_input_is_not_changed():
    data = bytearray(b"\x03\x11\x22\x02\x33")
    decode(data)
    assert data == bytearray(b"\x03\x11\x22\x02\x33")
