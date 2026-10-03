import pytest
from leb128 import encode_signed


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (0, "00"),
        (1, "01"),
        (-1, "7f"),
        (2, "02"),
        (-2, "7e"),
        (63, "3f"),
        (64, "c000"),
        (-64, "40"),
        (-65, "bf7f"),
        (127, "ff00"),
        (-127, "817f"),
        (128, "8001"),
        (-128, "807f"),
        (-129, "ff7e"),
        (8191, "ff3f"),
        (8192, "80c000"),
        (-8192, "8040"),
        (-8193, "ffbf7f"),
        (-123456, "c0bb78"),
        (2**63 - 1, "ffffffffffffffffff00"),
        (-(2**63), "8080808080808080807f"),
    ],
)
def test_known_encodings(value, encoded):
    assert encode_signed(value) == bytes.fromhex(encoded)


def test_the_boundaries_of_each_length():
    for k in range(1, 9):
        top = 2 ** (7 * k - 1)
        assert len(encode_signed(top - 1)) == k
        assert len(encode_signed(top)) == k + 1
        assert len(encode_signed(-top)) == k
        assert len(encode_signed(-top - 1)) == k + 1


def test_the_sign_is_bit_6_of_the_last_byte():
    for value in range(-300, 300):
        encoded = encode_signed(value)
        assert bool(encoded[-1] & 0x40) is (value < 0), value
        assert all(b & 0x80 for b in encoded[:-1])
        assert not encoded[-1] & 0x80


def test_max_bits_does_not_change_the_bytes_for_values_that_fit():
    for value in (0, 1, -1, 63, -64, 100, -100):
        base = encode_signed(value)
        for bits in (8, 9, 16, 32, 64, 128):
            assert encode_signed(value, bits) == base
            assert encode_signed(value, max_bits=bits) == base
    assert encode_signed(-200, 9) == b"\xb8\x7e"


def test_one_bit_signed_type_holds_only_minus_one_and_zero():
    assert encode_signed(-1, 1) == b"\x7f"
    assert encode_signed(0, 1) == b"\x00"
