import pytest
from base32 import decode


@pytest.mark.parametrize(
    "text",
    ["M", "MZX", "MZXW6Y", "MZXW6YTBM", "MZXW6YTBMZX", "MZXW6YTBMZXW6Y", "A", "AAA", "AAAAAA"],
)
def test_a_letter_count_no_encoder_produces_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize("text", ["M=======", "MZX=====", "MZXW6Y==", "MZXW6Y=", "MZX="])
def test_the_same_counts_with_padding_also_raise_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize("letters", [2, 4, 5, 7, 8, 10, 12, 13, 15, 16])
def test_the_good_letter_counts_decode(letters):
    assert isinstance(decode("A" * letters), bytes)
