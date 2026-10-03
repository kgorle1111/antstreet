import pytest
from qpdecode import decode_str


def test_the_bytes_are_read_as_utf_8_by_default():
    assert decode_str("caf=C3=A9") == "café"
    assert decode_str("=E2=82=AC 5") == "€ 5"
    assert decode_str("plain") == "plain"
    assert decode_str("") == ""
    assert type(decode_str("a")) is str


def test_another_charset_can_be_given_by_position_or_name():
    assert decode_str("caf=E9", "latin-1") == "café"
    assert decode_str("caf=E9", charset="iso-8859-1") == "café"
    assert decode_str("=A4", charset="iso-8859-15") == "€"
    assert decode_str("a", "ascii") == "a"


def test_the_rules_of_decode_apply_first():
    assert decode_str("a  \r\nb=\r\nc=3D") == "a\r\nbc="
    assert decode_str("=3D=41") == "=A"


@pytest.mark.parametrize(
    ("text", "charset"),
    [("=C3", "utf-8"), ("=FF", "utf-8"), ("=C3=28", "utf-8"), ("=E9", "ascii"), ("=80", "ascii")],
)
def test_bytes_that_are_not_valid_in_the_charset_raise_value_error(text, charset):
    with pytest.raises(ValueError):
        decode_str(text, charset)


def test_an_unknown_charset_raises_lookup_error():
    with pytest.raises(LookupError):
        decode_str("abc", "no-such-charset")
    with pytest.raises(LookupError):
        decode_str("abc", charset="utf-99")


@pytest.mark.parametrize("text", ["=G1", "=1", "café"])
def test_bad_text_raises_value_error_as_in_decode(text):
    with pytest.raises(ValueError):
        decode_str(text)


@pytest.mark.parametrize("text", [b"abc", None, 5, ["a"]])
def test_a_text_that_is_not_a_str_raises_type_error(text):
    with pytest.raises(TypeError):
        decode_str(text)
