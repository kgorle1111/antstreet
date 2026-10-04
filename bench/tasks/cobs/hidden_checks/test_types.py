import pytest
from cobs import decode, encode


@pytest.mark.parametrize("value", ["abc", "", None, 5, [1, 2], (1,), memoryview(b"ab"), 1.5, {1}])
def test_encode_rejects_anything_but_bytes_and_bytearray(value):
    with pytest.raises(TypeError):
        encode(value)


@pytest.mark.parametrize("value", ["\x01", "", None, 5, [1], (1,), memoryview(b"\x01"), 1.5])
def test_decode_rejects_anything_but_bytes_and_bytearray(value):
    with pytest.raises(TypeError):
        decode(value)


def test_a_type_error_comes_before_the_empty_input_error():
    # an empty str is the wrong type, not an empty packet
    with pytest.raises(TypeError):
        decode("")
    with pytest.raises(ValueError):
        decode(b"")


def test_encode_accepts_bytes_and_bytearray_alike():
    for data in (b"", b"\x00", b"abc", bytes(range(256))):
        assert encode(bytearray(data)) == encode(data)
        assert decode(bytearray(encode(data))) == decode(encode(data)) == data
