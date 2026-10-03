import pytest
from base32 import decode


@pytest.mark.parametrize(
    "text",
    [
        "MZXW6YT0",
        "MZXW6YT1",
        "MZXW6YT8",
        "MZXW6YT9",
        "MZXW 6YTB",
        "MZXW6YTB\n",
        " MZXW6YTB",
        "MZXW6YT\tB",
        "MZXW-6YTB",
        "MZXW6YT!",
        "MZXW6YT_",
        "MZXW6YT\u00c9",
        "MZXW6YT\u0661",  # an Arabic-Indic digit
        "MZXW6YT\uff22",  # a full-width letter
        "M\x00XW6YTB",
    ],
)
def test_a_character_outside_the_alphabet_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


def test_every_character_but_the_alphabet_and_equals_is_rejected():
    good = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz234567=")
    for code in range(0, 256):
        ch = chr(code)
        if ch in good:
            continue
        with pytest.raises(ValueError):
            decode("MZXW6YT" + ch)
