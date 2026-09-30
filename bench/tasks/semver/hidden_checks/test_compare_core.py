import pytest
from semver import compare


def test_return_values_are_exactly_minus_one_zero_one():
    for a, b, expected in [("1.0.0", "2.0.0", -1), ("2.0.0", "1.0.0", 1), ("1.0.0", "1.0.0", 0)]:
        result = compare(a, b)
        assert result == expected
        assert type(result) is int


@pytest.mark.parametrize(
    "lower, higher",
    [
        ("1.0.0", "2.0.0"),
        ("1.0.0", "1.1.0"),
        ("1.0.0", "1.0.1"),
        ("1.9.0", "1.10.0"),
        ("1.2.9", "1.2.10"),
        ("2.0.0", "10.0.0"),
        ("1.999.999", "2.0.0"),
        ("0.0.1", "0.1.0"),
        ("0.0.0", "0.0.1"),
        ("99999999999999999999.0.0", "100000000000000000000.0.0"),
    ],
)
def test_numeric_ordering_of_core(lower, higher):
    assert compare(lower, higher) == -1
    assert compare(higher, lower) == 1


@pytest.mark.parametrize("v", ["0.0.0", "1.2.3", "1.2.3-rc.1", "10.10.10", "1.0.0-a.1.b"])
def test_equal_versions(v):
    assert compare(v, v) == 0


def test_core_beats_prerelease_and_build_content():
    assert compare("2.0.0-alpha", "1.9.9") == 1
    assert compare("1.0.1-alpha", "1.0.0") == 1
    assert compare("1.0.0-zzz", "1.0.1-aaa") == -1


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3", "01.2.3", "1.2.3 ", "", "1.2.3-", "x"])
def test_invalid_input_raises_value_error(bad):
    with pytest.raises(ValueError):
        compare(bad, "1.0.0")
    with pytest.raises(ValueError):
        compare("1.0.0", bad)


@pytest.mark.parametrize("bad", [None, 1, b"1.0.0"])
def test_non_string_raises_value_error(bad):
    with pytest.raises(ValueError):
        compare(bad, "1.0.0")
    with pytest.raises(ValueError):
        compare("1.0.0", bad)
