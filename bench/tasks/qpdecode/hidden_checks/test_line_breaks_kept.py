import pytest
from qpdecode import decode


@pytest.mark.parametrize(
    "text",
    [
        "a\r\nb",
        "a\nb",
        "a\r\nb\nc",
        "a\nb\r\nc",
        "a\r\n",
        "a\n",
        "a\r\n\r\nb",
        "a\n\nb",
        "\r\n",
        "\n",
        "\r\n\r\n",
        "\n\n\n",
        "line one\r\nline two\r\nline three\r\n",
    ],
)
def test_line_breaks_come_out_exactly_as_they_went_in(text):
    assert decode(text) == text.encode("ascii")


def test_crlf_stays_crlf_and_lf_stays_lf_in_one_text():
    assert decode("a\r\nb\nc\r\nd") == b"a\r\nb\nc\r\nd"


def test_escapes_and_line_breaks_together():
    assert decode("caf=C3=A9\r\nna=C3=AFve\nend") == b"caf\xc3\xa9\r\nna\xc3\xafve\nend"


def test_a_realistic_mail_body():
    text = (
        "Subject line caf=C3=A9\r\n"
        "\r\n"
        "Dear user,\r\n"
        "the total is 5=3D3+2 euro =E2=82=AC. See the long link http://example.com/a=\r\n"
        "b=3Dc for more.   \r\n"
        "Bye\r\n"
    )
    assert decode(text) == (
        b"Subject line caf\xc3\xa9\r\n\r\nDear user,\r\n"
        b"the total is 5=3+2 euro \xe2\x82\xac. "
        b"See the long link http://example.com/ab=c for more.\r\n"
        b"Bye\r\n"
    )
