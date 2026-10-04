import pytest
from base32 import decode


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("mzxw6ytboi======", b"foobar"),
        ("Mzxw6YtBoI======", b"foobar"),
        ("mzxw6ytboi", b"foobar"),
        ("my", b"f"),
        ("My======", b"f"),
        ("mzxw6yq=", b"foob"),
    ],
)
def test_lower_and_mixed_case_letters_are_accepted(text, raw):
    assert decode(text) == raw


@pytest.mark.parametrize(
    ("padded", "bare", "raw"),
    [
        ("MY======", "MY", b"f"),
        ("MZXQ====", "MZXQ", b"fo"),
        ("MZXW6===", "MZXW6", b"foo"),
        ("MZXW6YQ=", "MZXW6YQ", b"foob"),
        ("MZXW6YTB", "MZXW6YTB", b"fooba"),
        ("MZXW6YTBOI======", "MZXW6YTBOI", b"foobar"),
    ],
)
def test_padding_may_be_present_or_left_out(padded, bare, raw):
    assert decode(padded) == raw
    assert decode(bare) == raw


def test_the_empty_string_is_empty_bytes():
    assert decode("") == b""
