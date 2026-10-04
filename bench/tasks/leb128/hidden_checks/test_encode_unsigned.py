import pytest
from leb128 import encode_unsigned


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (0, "00"),
        (1, "01"),
        (127, "7f"),
        (128, "8001"),
        (129, "8101"),
        (255, "ff01"),
        (256, "8002"),
        (16383, "ff7f"),
        (16384, "808001"),
        (624485, "e58e26"),
        (2**21 - 1, "ffff7f"),
        (2**21, "80808001"),
        (2**32 - 1, "ffffffff0f"),
        (2**32, "8080808010"),
        (2**63, "80808080808080808001"),
        (2**64 - 1, "ffffffffffffffffff01"),
    ],
)
def test_known_encodings(value, encoded):
    assert encode_unsigned(value) == bytes.fromhex(encoded)


def test_the_result_is_bytes():
    assert type(encode_unsigned(0)) is bytes
    assert type(encode_unsigned(10**6)) is bytes


def test_the_encoding_is_the_shortest_possible():
    for bits in range(1, 64):
        assert len(encode_unsigned(2**bits - 1)) == -(-bits // 7)
        assert len(encode_unsigned(2**bits)) == bits // 7 + 1


def test_only_the_last_byte_has_a_clear_high_bit():
    for value in (0, 1, 127, 128, 300, 2**20, 2**35 + 17, 2**64 - 1):
        encoded = encode_unsigned(value)
        assert all(b & 0x80 for b in encoded[:-1])
        assert not encoded[-1] & 0x80


def test_a_value_only_has_a_zero_last_byte_when_it_is_zero():
    assert encode_unsigned(0) == b"\x00"
    for value in range(1, 3000):
        assert encode_unsigned(value)[-1] != 0, value


def test_max_bits_does_not_change_the_bytes_for_values_that_fit():
    for value in (0, 1, 100, 200):
        base = encode_unsigned(value)
        for bits in (8, 9, 16, 32, 64, 128):
            assert encode_unsigned(value, bits) == base
            assert encode_unsigned(value, max_bits=bits) == base
    assert encode_unsigned(300, 9) == b"\xac\x02"


def test_a_wide_max_bits_allows_big_values():
    value = 2**100 + 12345
    encoded = encode_unsigned(value, 128)
    assert len(encoded) == 15
    assert all(b & 0x80 for b in encoded[:-1]) and not encoded[-1] & 0x80


def test_a_one_bit_type_holds_zero_and_one():
    assert encode_unsigned(0, 1) == b"\x00"
    assert encode_unsigned(1, 1) == b"\x01"
