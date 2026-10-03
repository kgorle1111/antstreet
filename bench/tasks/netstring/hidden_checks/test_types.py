import pytest
from netstring import Decoder, encode


@pytest.mark.parametrize(
    "data", ["5:hello,", "", None, 5, [b"a"], memoryview(b"1:a,"), 1.5, ("a",)]
)
def test_feed_rejects_anything_but_bytes_and_bytearray(data):
    with pytest.raises(TypeError):
        Decoder().feed(data)


def test_a_type_error_does_not_break_the_decoder():
    d = Decoder()
    d.feed(b"3:a")
    with pytest.raises(TypeError):
        d.feed("bc,")
    assert d.feed(b"bc,") == [b"abc"]


def test_feed_accepts_a_bytearray_in_any_piece():
    d = Decoder()
    assert d.feed(bytearray(b"3:a")) == []
    assert d.feed(bytearray(b"bc,")) == [b"abc"]


def test_encode_and_decode_agree():
    payloads = [b"", b"a", b"hello", b"\x00" * 300, bytes(range(256)), b"1:a,"]
    assert Decoder().feed(b"".join(map(encode, payloads))) == payloads
