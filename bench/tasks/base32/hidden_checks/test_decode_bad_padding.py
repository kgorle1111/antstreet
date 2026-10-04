import pytest
from base32 import decode


@pytest.mark.parametrize(
    "text",
    [
        "MY=",
        "MY====",
        "MY=====",
        "MY=======",
        "MY========",
        "MZXQ===",
        "MZXQ=====",
        "MZXW6==",
        "MZXW6====",
        "MZXW6YQ==",
    ],
)
def test_the_wrong_amount_of_padding_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize(
    "text",
    ["MZXW6YTB=", "MZXW6YTB========", "MZXW6YTBOI=", "MZXW6YTBOI=====", "MZXW6YTBOI======="],
)
def test_padding_after_a_full_group_or_the_wrong_amount_after_a_part_group_raises(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize(
    "text",
    ["=", "==", "========", "=MY=====", "M=Y=====", "MY==X===", "MZXQ====MZXQ===="],
)
def test_equals_signs_anywhere_but_the_end_raise_value_error(text):
    with pytest.raises(ValueError):
        decode(text)
