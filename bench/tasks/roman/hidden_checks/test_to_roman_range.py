import pytest
from roman import to_roman


@pytest.mark.parametrize("bad", [0, -1, -4, 4000, 4001, 10000, 10**9])
def test_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        to_roman(bad)


def test_both_ends_of_the_range_are_accepted():
    assert to_roman(1) == "I"
    assert to_roman(3999) == "MMMCMXCIX"
