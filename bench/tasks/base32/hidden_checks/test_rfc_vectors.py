import pytest
from base32 import decode, encode

VECTORS = [
    (b"", ""),
    (b"f", "MY======"),
    (b"fo", "MZXQ===="),
    (b"foo", "MZXW6==="),
    (b"foob", "MZXW6YQ="),
    (b"fooba", "MZXW6YTB"),
    (b"foobar", "MZXW6YTBOI======"),
]


@pytest.mark.parametrize(("raw", "text"), VECTORS)
def test_encode_matches_the_rfc_vectors(raw, text):
    assert encode(raw) == text


@pytest.mark.parametrize(("raw", "text"), VECTORS)
def test_decode_matches_the_rfc_vectors(raw, text):
    assert decode(text) == raw


def test_a_longer_text_and_the_result_types():
    assert encode(b"Hello, World!") == "JBSWY3DPFQQFO33SNRSCC==="
    assert decode("JBSWY3DPFQQFO33SNRSCC===") == b"Hello, World!"
    assert type(encode(b"x")) is str
    assert type(decode("MY======")) is bytes
    assert type(decode("")) is bytes
