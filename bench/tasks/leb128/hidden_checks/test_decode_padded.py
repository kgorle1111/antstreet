import pytest
from leb128 import decode_signed, decode_unsigned


@pytest.mark.parametrize(
    ("data", "value"),
    [
        (b"\x80\x00", 0),
        (b"\x80\x80\x00", 0),
        (b"\x81\x00", 1),
        (b"\xff\x80\x00", 127),
        (b"\xe5\x8e\xa6\x00", 624485),
        (b"\x80" * 9 + b"\x00", 0),
        (b"\x85\x80\x80\x00", 5),
    ],
)
def test_unsigned_numbers_written_with_extra_bytes_are_accepted(data, value):
    assert decode_unsigned(data) == (value, len(data))


@pytest.mark.parametrize(
    ("data", "value"),
    [
        (b"\x80\x00", 0),
        (b"\xff\x7f", -1),
        (b"\xff\xff\x7f", -1),
        (b"\xff" * 9 + b"\x7f", -1),
        (b"\xc0\x80\x00", 64),
        (b"\xc0\xff\x7f", -64),
        (b"\xfe\xff\x7f", -2),
        (b"\x81\x80\x00", 1),
    ],
)
def test_signed_numbers_written_with_extra_bytes_are_accepted(data, value):
    assert decode_signed(data) == (value, len(data))


def test_extra_bytes_do_not_change_where_the_next_number_starts():
    assert decode_unsigned(b"\x80\x00\x05") == (0, 2)
    assert decode_unsigned(b"\x80\x00\x05", 2) == (5, 3)
    assert decode_signed(b"\xff\x7f\x05", 0) == (-1, 2)


def test_extra_bytes_are_accepted_up_to_the_limit_and_not_beyond():
    assert decode_unsigned(b"\x80\x00", 0, 8) == (0, 2)
    with pytest.raises(OverflowError):
        decode_unsigned(b"\x80\x80\x00", 0, 8)
    assert decode_signed(b"\xff\x7f", 0, 8) == (-1, 2)
    with pytest.raises(OverflowError):
        decode_signed(b"\xff\xff\x7f", 0, 8)
    assert decode_unsigned(b"\x80\x00", 0, 14) == (0, 2)
    with pytest.raises(OverflowError):
        decode_unsigned(b"\x80\x80\x00", 0, 14)
