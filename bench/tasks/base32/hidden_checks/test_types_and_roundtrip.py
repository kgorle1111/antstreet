import pytest
from base32 import decode, encode


@pytest.mark.parametrize("data", ["abc", "", None, 5, ["a"], (1, 2), memoryview(b"ab"), 1.5])
def test_encode_rejects_anything_but_bytes_and_bytearray(data):
    with pytest.raises(TypeError):
        encode(data)


@pytest.mark.parametrize("text", [b"MY======", None, 5, ["MY"], bytearray(b"MY"), 1.5])
def test_decode_rejects_anything_but_str(text):
    with pytest.raises(TypeError):
        decode(text)


def test_encode_accepts_a_bytearray():
    assert encode(bytearray(b"foobar")) == "MZXW6YTBOI======"
    assert encode(bytearray()) == ""


def test_every_length_round_trips_both_ways():
    for n in range(0, 80):
        raw = bytes((i * 131 + n) & 255 for i in range(n))
        assert decode(encode(raw)) == raw
        assert decode(encode(raw, pad=False)) == raw


def test_every_byte_value_round_trips():
    raw = bytes(range(256))
    assert decode(encode(raw)) == raw
    assert decode(encode(raw, pad=False)) == raw
    assert decode(encode(raw).lower()) == raw
