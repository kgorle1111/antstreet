import pytest
from base32 import decode, encode


def _accepted(text):
    try:
        decode(text)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize(
    "text",
    ["MZ", "MZ======", "MZXR", "MZXR====", "MZXW7", "MZXW7===", "MZXW6YR", "MZXW6YR=", "AB", "A7"],
)
def test_nonzero_bits_left_in_the_last_letter_raise_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


def test_in_a_one_byte_message_the_second_letter_must_end_in_two_zero_bits():
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    assert [ch for ch in letters if _accepted("A" + ch)] == list("AEIMQUY") + ["4"]


def test_zero_tail_bits_decode():
    assert decode("MY") == b"f"
    assert decode("AA") == b"\x00"
    assert decode("74") == b"\xff"
    assert decode("777Q") == b"\xff\xff"


def test_everything_encode_writes_is_accepted():
    for n in range(0, 12):
        raw = bytes((i * 37 + 11) & 255 for i in range(n))
        assert decode(encode(raw)) == raw
