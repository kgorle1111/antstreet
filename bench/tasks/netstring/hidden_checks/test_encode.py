import pytest
from netstring import encode


@pytest.mark.parametrize(
    ("payload", "framed"),
    [
        (b"hello", b"5:hello,"),
        (b"", b"0:,"),
        (b"a", b"1:a,"),
        (b"hello world!", b"12:hello world!,"),
        (b"3:abc,", b"6:3:abc,,"),
        (b",", b"1:,,"),
        (b":", b"1::,"),
        (b"\n\x00\xff", b"3:\n\x00\xff,"),
        (b"\xc3\xa9", b"2:\xc3\xa9,"),
    ],
)
def test_known_frames(payload, framed):
    assert encode(payload) == framed


def test_the_length_is_written_in_decimal_without_padding():
    assert encode(b"x" * 9) == b"9:" + b"x" * 9 + b","
    assert encode(b"x" * 10) == b"10:" + b"x" * 10 + b","
    assert encode(b"x" * 100) == b"100:" + b"x" * 100 + b","
    assert encode(b"x" * 12345).startswith(b"12345:")
    assert len(encode(b"x" * 12345)) == 5 + 1 + 12345 + 1


def test_a_bytearray_is_accepted_and_the_result_is_bytes():
    assert encode(bytearray(b"abc")) == b"3:abc,"
    assert type(encode(bytearray(b"abc"))) is bytes
    assert type(encode(b"")) is bytes


@pytest.mark.parametrize("payload", ["hello", "", None, 5, [b"a"], memoryview(b"ab"), 1.5])
def test_anything_but_bytes_or_bytearray_raises_type_error(payload):
    with pytest.raises(TypeError):
        encode(payload)
