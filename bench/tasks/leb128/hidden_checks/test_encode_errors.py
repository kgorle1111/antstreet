import pytest
from leb128 import encode_signed, encode_unsigned


@pytest.mark.parametrize("value", [-1, -2, -(2**63), 2**64, 2**64 + 1, 2**100, -(2**100)])
def test_an_unsigned_value_outside_the_default_range_raises_overflow_error(value):
    with pytest.raises(OverflowError):
        encode_unsigned(value)


@pytest.mark.parametrize("value", [2**63, 2**63 + 1, 2**64, -(2**63) - 1, -(2**64), 2**100])
def test_a_signed_value_outside_the_default_range_raises_overflow_error(value):
    with pytest.raises(OverflowError):
        encode_signed(value)


@pytest.mark.parametrize(
    ("value", "bits"),
    [(256, 8), (255, 8), (2**16, 16), (128, 7), (2, 1), (2**32, 32), (-1, 8), (1, 1)],
)
def test_unsigned_range_follows_max_bits(value, bits):
    if 0 <= value < 2**bits:
        encode_unsigned(value, bits)
    else:
        with pytest.raises(OverflowError):
            encode_unsigned(value, bits)


@pytest.mark.parametrize(
    ("value", "bits", "fits"),
    [
        (127, 8, True),
        (128, 8, False),
        (-128, 8, True),
        (-129, 8, False),
        (32767, 16, True),
        (32768, 16, False),
        (-32768, 16, True),
        (-32769, 16, False),
        (0, 1, True),
        (-1, 1, True),
        (1, 1, False),
        (-2, 1, False),
        (2**31 - 1, 32, True),
        (2**31, 32, False),
        (-(2**31), 32, True),
        (-(2**31) - 1, 32, False),
        (2**100, 128, True),
        (2**127, 128, False),
    ],
)
def test_signed_range_follows_max_bits(value, bits, fits):
    if fits:
        encode_signed(value, bits)
    else:
        with pytest.raises(OverflowError):
            encode_signed(value, bits)


def test_the_largest_values_of_the_default_width_are_accepted():
    assert encode_unsigned(2**64 - 1)
    assert encode_signed(2**63 - 1)
    assert encode_signed(-(2**63))
    assert encode_unsigned(0)


@pytest.mark.parametrize("value", ["1", None, 1.0, 1.5, True, False, b"\x01", [1], (1,), 1 + 0j])
def test_a_value_that_is_not_an_int_raises_type_error(value):
    with pytest.raises(TypeError):
        encode_unsigned(value)
    with pytest.raises(TypeError):
        encode_signed(value)


@pytest.mark.parametrize("bits", ["8", None, 8.0, True, b"8", [8]])
def test_a_max_bits_that_is_not_an_int_raises_type_error(bits):
    with pytest.raises(TypeError):
        encode_unsigned(1, bits)
    with pytest.raises(TypeError):
        encode_signed(1, bits)
    with pytest.raises(TypeError):
        encode_unsigned(1, max_bits=bits)


@pytest.mark.parametrize("bits", [0, -1, -64])
def test_a_max_bits_below_one_raises_value_error(bits):
    with pytest.raises(ValueError):
        encode_unsigned(0, bits)
    with pytest.raises(ValueError):
        encode_signed(0, bits)
