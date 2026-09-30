import pytest
from semver import parse


@pytest.mark.parametrize("bad", ["01.2.3", "1.02.3", "1.2.03", "00.0.0", "0.00.0", "0.0.00"])
def test_leading_zero_in_core_raises(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize(
    "bad",
    ["1.2.3-01", "1.2.3-00", "1.2.3-a.01", "1.2.3-01.a", "1.2.3-1.2.03", "1.2.3-007+build"],
)
def test_leading_zero_in_numeric_prerelease_identifier_raises(bad):
    with pytest.raises(ValueError):
        parse(bad)


def test_zero_itself_is_fine():
    assert parse("0.0.0-0") == (0, 0, 0, (0,), ())
    assert parse("0.10.100") == (0, 10, 100, (), ())


def test_zeros_in_build_and_alphanumeric_identifiers_are_fine():
    assert parse("1.2.3+007") == (1, 2, 3, (), ("007",))
    assert parse("1.2.3-0x1f") == (1, 2, 3, ("0x1f",), ())
    assert parse("1.2.3-00a") == (1, 2, 3, ("00a",), ())
