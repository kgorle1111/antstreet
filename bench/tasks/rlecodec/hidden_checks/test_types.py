import pytest
from rlecodec import decode, encode


@pytest.mark.parametrize("value", [b"aab", None, 5, ["a"], ("a",), 1.5, bytearray(b"a")])
def test_encode_rejects_anything_but_str(value):
    with pytest.raises(TypeError):
        encode(value)


@pytest.mark.parametrize("value", [b"2a", None, 5, ["2a"], ("2a",), 1.5, bytearray(b"2a")])
def test_decode_rejects_anything_but_str(value):
    with pytest.raises(TypeError):
        decode(value)


def test_the_text_type_is_checked_even_for_empty_values():
    for func in (encode, decode):
        with pytest.raises(TypeError):
            func(b"")
        with pytest.raises(TypeError):
            func(None)
