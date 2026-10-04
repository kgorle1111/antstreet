import pytest
from qpdecode import decode


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("a  \r\nb", b"a\r\nb"),
        ("a \nb", b"a\nb"),
        ("a\t\r\nb", b"a\r\nb"),
        ("a \t \t\nb", b"a\nb"),
        ("a  \r\nb\t\n", b"a\r\nb\n"),
        ("a  ", b"a"),
        ("a\t", b"a"),
        ("a \t ", b"a"),
        ("   ", b""),
        ("\t", b""),
        (" ", b""),
        ("   \r\n", b"\r\n"),
        ("a\r\n   \r\nb", b"a\r\n\r\nb"),
        ("a\n \t\nb", b"a\n\nb"),
    ],
)
def test_spaces_and_tabs_at_the_end_of_a_line_are_dropped(text, raw):
    assert decode(text) == raw


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("a=20", b"a "),
        ("a=09", b"a\t"),
        ("a =20", b"a  "),
        ("a=20=20", b"a  "),
        ("a=20\r\nb", b"a \r\nb"),
        ("a=09\nb", b"a\t\nb"),
        ("=20\r\n=20", b" \r\n "),
        ("a=20  \r\nb", b"a \r\nb"),
        ("a=3D  ", b"a="),
    ],
)
def test_whitespace_written_as_an_escape_is_kept(text, raw):
    assert decode(text) == raw


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("a  =\r\nb", b"a  b"),
        ("a \t=\nb", b"a \tb"),
        ("a  =", b"a  "),
        ("  =\r\n  ", b"  "),
        (" =\n", b" "),
    ],
)
def test_whitespace_before_a_soft_line_break_is_content(text, raw):
    assert decode(text) == raw


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("a b", b"a b"),
        ("a  b\t\tc", b"a  b\t\tc"),
        (" a", b" a"),
        ("\ta\r\n  b", b"\ta\r\n  b"),
        ("  a  b  ", b"  a  b"),
    ],
)
def test_whitespace_inside_a_line_and_at_its_start_is_kept(text, raw):
    assert decode(text) == raw


def test_only_the_whitespace_at_the_very_end_of_each_line_goes():
    assert decode("a  b  \r\nc  d  ") == b"a  b\r\nc  d"
