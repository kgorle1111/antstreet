import pytest
from leb128 import decode_signed, decode_unsigned


def test_the_largest_64_bit_unsigned_value_is_accepted_and_one_more_is_not():
    assert decode_unsigned(b"\xff" * 9 + b"\x01") == (2**64 - 1, 10)
    for last in (0x02, 0x03, 0x04, 0x10, 0x7F):
        with pytest.raises(OverflowError):
            decode_unsigned(b"\xff" * 9 + bytes([last]))
    with pytest.raises(OverflowError):
        decode_unsigned(b"\x80" * 9 + b"\x02")


def test_the_64_bit_signed_extremes_are_accepted_and_beyond_them_is_not():
    assert decode_signed(b"\xff" * 9 + b"\x00") == (2**63 - 1, 10)
    assert decode_signed(b"\x80" * 9 + b"\x7f") == (-(2**63), 10)
    assert decode_signed(b"\xff" * 9 + b"\x7f") == (-1, 10)
    with pytest.raises(OverflowError):
        decode_signed(b"\x80" * 9 + b"\x01")  # 2**63
    with pytest.raises(OverflowError):
        decode_signed(b"\xff" * 9 + b"\x01")  # 2**64 - 1
    with pytest.raises(OverflowError):
        decode_signed(b"\xff" * 9 + b"\x3f")
    with pytest.raises(OverflowError):
        decode_signed(
            b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x40"
        )  # 2**63 - 1 - 2**69, below -2**63


def test_a_run_of_continuation_bytes_that_reaches_the_limit_is_overflow_error():
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(OverflowError):
            func(b"\x80" * 10)
        with pytest.raises(OverflowError):
            func(b"\xff" * 10)
        with pytest.raises(OverflowError):
            func(b"\x80" * 10 + b"\x00")
        with pytest.raises(OverflowError):
            func(b"\x80" * 25)


def test_the_limit_is_checked_at_the_offset_too():
    with pytest.raises(OverflowError):
        decode_unsigned(b"\x01" + b"\x80" * 10 + b"\x00", 1)
    assert decode_unsigned(b"\x01" + b"\x80" * 9 + b"\x00", 1) == (0, 11)


def test_the_byte_limit_is_ceil_of_max_bits_over_7():
    # max_bits -> bytes allowed: 1..7 -> 1, 8..14 -> 2, 15..21 -> 3, 22..28 -> 4, 29..35 -> 5
    for bits, limit in [
        (1, 1),
        (7, 1),
        (8, 2),
        (14, 2),
        (15, 3),
        (21, 3),
        (22, 4),
        (32, 5),
        (35, 5),
        (36, 6),
    ]:
        zeros_ok = b"\x80" * (limit - 1) + b"\x00"
        assert decode_unsigned(zeros_ok, 0, bits) == (0, limit), bits
        assert decode_signed(zeros_ok, 0, bits) == (0, limit), bits
        for func in (decode_unsigned, decode_signed):
            with pytest.raises(OverflowError):
                func(b"\x80" * limit + b"\x00", 0, bits)
            with pytest.raises(OverflowError):
                func(b"\x80" * limit, 0, bits)


def test_a_32_bit_unsigned_number():
    assert decode_unsigned(b"\xff\xff\xff\xff\x0f", 0, 32) == (2**32 - 1, 5)
    with pytest.raises(OverflowError):
        decode_unsigned(b"\x80\x80\x80\x80\x10", 0, 32)
    with pytest.raises(OverflowError):
        decode_unsigned(b"\xff\xff\xff\xff\x1f", 0, 32)
    with pytest.raises(OverflowError):
        decode_unsigned(b"\xff\xff\xff\xff\xff\x00", 0, 32)


def test_a_32_bit_signed_number():
    assert decode_signed(b"\xff\xff\xff\xff\x07", 0, 32) == (2**31 - 1, 5)
    assert decode_signed(b"\x80\x80\x80\x80\x78", 0, 32) == (-(2**31), 5)
    with pytest.raises(OverflowError):
        decode_signed(b"\x80\x80\x80\x80\x08", 0, 32)  # 2**31
    with pytest.raises(OverflowError):
        decode_signed(b"\xff\xff\xff\xff\x77", 0, 32)  # below -2**31
    with pytest.raises(OverflowError):
        decode_signed(b"\x80\x80\x80\x80\x70", 0, 32)  # -2**32 + ... below the range


@pytest.mark.parametrize(
    ("bits", "data", "value"),
    [
        (7, b"\x7f", 127),
        (8, b"\xff\x01", 255),
        (9, b"\xff\x03", 511),
        (14, b"\xff\x7f", 16383),
        (1, b"\x01", 1),
        (1, b"\x00", 0),
    ],
)
def test_the_largest_unsigned_value_of_a_width(bits, data, value):
    assert decode_unsigned(data, 0, bits) == (value, len(data))


@pytest.mark.parametrize(
    ("bits", "data"),
    [
        (7, b"\x80\x01"),
        (8, b"\x80\x02"),
        (9, b"\x80\x04"),
        (1, b"\x02"),
        (1, b"\x7f"),
        (14, b"\x80\x80\x01"),
    ],
)
def test_one_more_than_the_largest_unsigned_value_of_a_width_is_overflow(bits, data):
    with pytest.raises(OverflowError):
        decode_unsigned(data, 0, bits)


@pytest.mark.parametrize(
    ("bits", "data", "value"),
    [
        (7, b"\x3f", 63),
        (7, b"\x40", -64),
        (8, b"\xff\x00", 127),
        (8, b"\x80\x7f", -128),
        (1, b"\x00", 0),
        (1, b"\x7f", -1),
        (9, b"\xff\x01", 255),
        (9, b"\x80\x7e", -256),
    ],
)
def test_the_extremes_of_a_signed_width(bits, data, value):
    assert decode_signed(data, 0, bits) == (value, len(data))


@pytest.mark.parametrize(
    ("bits", "data"),
    [
        (7, b"\xc0\x00"),
        (7, b"\xbf\x7f"),
        (8, b"\x80\x01"),
        (8, b"\xff\x7e"),
        (1, b"\x01"),
        (1, b"\x7e"),
        (9, b"\x80\x02"),
    ],
)
def test_one_beyond_a_signed_width_is_overflow(bits, data):
    with pytest.raises(OverflowError):
        decode_signed(data, 0, bits)


@pytest.mark.parametrize("bits", [0, -1, -64])
def test_a_max_bits_below_one_raises_value_error(bits):
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(ValueError):
            func(b"\x01", 0, bits)


@pytest.mark.parametrize("bits", ["64", None, 64.0, True, b"8"])
def test_a_max_bits_that_is_not_an_int_raises_type_error(bits):
    for func in (decode_unsigned, decode_signed):
        with pytest.raises(TypeError):
            func(b"\x01", 0, bits)
        with pytest.raises(TypeError):
            func(b"\x01", max_bits=bits)
