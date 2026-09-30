import pytest
from roman import to_roman


@pytest.mark.parametrize("bad", [4.0, 3.5, 1.0, "5", "V", None, [5], (5,)])
def test_non_integers_raise(bad):
    with pytest.raises(ValueError):
        to_roman(bad)


@pytest.mark.parametrize("bad", [True, False])
def test_bool_raises(bad):
    with pytest.raises(ValueError):
        to_roman(bad)
