import pytest
from slugify import slugify


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_limit_below_one_raises(bad):
    with pytest.raises(ValueError):
        slugify("hello", max_length=bad)
