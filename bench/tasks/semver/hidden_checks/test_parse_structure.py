import pytest
from semver import parse


@pytest.mark.parametrize(
    "bad",
    ["", "1", "1.2", "1.2.", ".2.3", "1..3", "1.2.3.4", "1.2.x", "a.b.c", "1.2.3.", "..."],
)
def test_wrong_number_of_parts_raises(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "1.2.3-",
        "1.2.3+",
        "1.2.3-+build",
        "1.2.3-a+",
        "1.2.3-a..b",
        "1.2.3-.a",
        "1.2.3-a.",
        "1.2.3+a..b",
        "1.2.3+.a",
        "1.2.3+a.",
        "1.2.3-a.-.",
    ],
)
def test_empty_identifiers_raise(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize("bad", ["v1.2.3", "V1.2.3", "+1.2.3", "-1.2.3", "1.-2.3", "1.+2.3"])
def test_prefix_and_signs_raise(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize("bad", ["1.2.3-a+b+c", "1.2.3+a-b+c", "1.2.3++b"])
def test_second_plus_raises(bad):
    with pytest.raises(ValueError):
        parse(bad)
