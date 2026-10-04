import pytest
from cobs import encode


def nonzero(n, start=1):
    """n non-zero bytes: start, start+1, ... wrapping inside 1..255."""
    return bytes((start - 1 + i) % 255 + 1 for i in range(n))


def test_253_non_zero_bytes_fit_in_one_block():
    data = nonzero(253)
    assert encode(data) == bytes([254]) + data


def test_254_non_zero_bytes_are_one_full_block_with_nothing_after_it():
    data = bytes(range(1, 255))
    assert len(data) == 254
    assert encode(data) == b"\xff" + data


def test_255_non_zero_bytes_are_a_full_block_and_a_block_of_one():
    data = bytes(range(1, 256))
    assert len(data) == 255
    assert encode(data) == b"\xff" + data[:254] + b"\x02" + data[254:]
    assert encode(data) == b"\xff" + bytes(range(1, 255)) + b"\x02\xff"


def test_254_non_zero_bytes_then_a_zero_end_with_two_empty_blocks():
    data = bytes(range(2, 256))
    assert len(data) == 254
    assert encode(data + b"\x00") == b"\xff" + data + b"\x01\x01"


def test_254_non_zero_bytes_then_a_zero_and_more():
    data = bytes(range(2, 256))
    assert encode(data + b"\x00\x07") == b"\xff" + data + b"\x01\x02\x07"
    assert encode(data + b"\x00\x00") == b"\xff" + data + b"\x01\x01\x01"


def test_253_non_zero_bytes_then_a_zero_use_the_zero_of_the_block():
    data = bytes(range(3, 256))
    assert len(data) == 253
    assert encode(data + b"\x00\x01") == b"\xfe" + data + b"\x02\x01"
    assert encode(data + b"\x00") == b"\xfe" + data + b"\x01"


def test_a_zero_then_254_non_zero_bytes():
    data = bytes(range(1, 255))
    assert encode(b"\x00" + data) == b"\x01\xff" + data


def test_two_full_blocks_have_nothing_after_them():
    data = nonzero(508)
    assert encode(data) == b"\xff" + data[:254] + b"\xff" + data[254:]


def test_two_full_blocks_and_one_more_byte():
    data = nonzero(509)
    assert encode(data) == b"\xff" + data[:254] + b"\xff" + data[254:508] + b"\x02" + data[508:]


def test_a_run_of_508_then_a_zero_has_two_full_blocks_then_two_empty_ones():
    data = nonzero(508)
    assert encode(data + b"\x00") == b"\xff" + data[:254] + b"\xff" + data[254:] + b"\x01\x01"


def test_a_long_run_with_a_remainder_before_a_zero():
    data = nonzero(300)
    assert encode(data + b"\x00" + b"\x05") == (
        b"\xff" + data[:254] + bytes([47]) + data[254:] + b"\x02\x05"
    )
    assert encode(data) == b"\xff" + data[:254] + bytes([47]) + data[254:]


@pytest.mark.parametrize("size", [1, 2, 100, 252, 253, 254, 255, 256, 507, 508, 509, 762, 1000])
def test_a_run_of_any_size_is_cut_into_blocks_of_254(size):
    data = nonzero(size)
    out = encode(data)
    full, rest = divmod(size, 254)
    expected = b""
    for i in range(full):
        expected += b"\xff" + data[i * 254 : (i + 1) * 254]
    if rest:
        expected += bytes([rest + 1]) + data[full * 254 :]
    assert out == expected


def test_the_length_bound_holds_at_the_edges():
    for size in (0, 1, 253, 254, 255, 508, 509, 762):
        for data in (nonzero(size), bytes(size), nonzero(size) + b"\x00"):
            assert len(encode(data)) <= len(data) + len(data) // 254 + 1
