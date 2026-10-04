import pytest
from base32 import encode


@pytest.mark.parametrize("size", range(0, 21))
def test_padded_output_length_is_a_multiple_of_eight(size):
    text = encode(bytes(range(1, size + 1)))
    assert len(text) % 8 == 0
    assert len(text) == -(-size // 5) * 8


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        (b"", ""),
        (b"f", "MY"),
        (b"fo", "MZXQ"),
        (b"foo", "MZXW6"),
        (b"foob", "MZXW6YQ"),
        (b"fooba", "MZXW6YTB"),
        (b"foobar", "MZXW6YTBOI"),
    ],
)
def test_pad_false_writes_no_equals_signs(raw, text):
    assert encode(raw, pad=False) == text
    assert encode(raw, False) == text


def test_pad_true_is_the_default_and_can_be_given():
    assert encode(b"fo") == encode(b"fo", pad=True) == "MZXQ===="


def test_the_padding_amount_depends_on_the_remainder_of_the_length():
    assert [encode(b"a" * n).count("=") for n in range(1, 11)] == [6, 4, 3, 1, 0, 6, 4, 3, 1, 0]
