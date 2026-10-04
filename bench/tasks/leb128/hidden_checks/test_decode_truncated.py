import pytest
from leb128 import decode_signed, decode_unsigned, encode_signed, encode_unsigned

BOTH = (decode_unsigned, decode_signed)


@pytest.mark.parametrize(
    "data", [b"", b"\x80", b"\xff", b"\x80\x80", b"\xe5\x8e", b"\xff" * 9, b"\x80" * 5]
)
def test_data_that_ends_inside_a_number_raises_value_error(data):
    for func in BOTH:
        with pytest.raises(ValueError):
            func(data)


def test_truncation_is_judged_from_the_offset():
    for func in BOTH:
        with pytest.raises(ValueError):
            func(b"\x01\x80", 1)
        with pytest.raises(ValueError):
            func(b"\x01\x02\xff\xff", 2)
        with pytest.raises(ValueError):
            func(b"\x01", 1)


def test_cutting_a_valid_encoding_short_raises_value_error():
    for value in (128, 624485, 2**32, 2**63):
        encoded = encode_unsigned(value)
        for cut in range(0, len(encoded)):
            with pytest.raises(ValueError):
                decode_unsigned(encoded[:cut])
    for value in (-123456, 64, -(2**63)):
        encoded = encode_signed(value)
        for cut in range(0, len(encoded)):
            with pytest.raises(ValueError):
                decode_signed(encoded[:cut])


def test_a_complete_number_followed_by_a_truncated_one_reads_the_first_fine():
    data = b"\x05\x80"
    assert decode_unsigned(data) == (5, 1)
    with pytest.raises(ValueError):
        decode_unsigned(data, 1)


def test_the_data_ending_before_the_byte_limit_is_truncation_and_not_overflow():
    # 9 bytes with the high bit set are fewer than the 10 allowed at 64 bits
    for func in BOTH:
        with pytest.raises(ValueError):
            func(b"\x80" * 9)
        with pytest.raises(ValueError):
            func(b"\xff" * 4, 0, 32)  # 4 of the 5 bytes a 32-bit number may use
