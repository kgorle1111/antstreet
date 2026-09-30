import itertools

import pytest
from semver import compare

# The precedence chain from the SemVer 2.0.0 specification, lowest first.
CHAIN = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
]


def test_spec_chain_every_pair():
    for (i, low), (j, high) in itertools.combinations(enumerate(CHAIN), 2):
        assert i < j
        assert compare(low, high) == -1, (low, high)
        assert compare(high, low) == 1, (high, low)


def test_prerelease_is_lower_than_release():
    assert compare("1.0.0-0", "1.0.0") == -1
    assert compare("1.0.0", "1.0.0-rc.1") == 1
    assert compare("1.0.0-zzz.999", "1.0.0") == -1


def test_numeric_identifiers_compare_as_numbers():
    assert compare("1.0.0-2", "1.0.0-10") == -1
    assert compare("1.0.0-alpha.9", "1.0.0-alpha.10") == -1
    assert compare("1.0.0-99999999999999999999", "1.0.0-100000000000000000000") == -1
    assert compare("1.0.0-0", "1.0.0-1") == -1


def test_numeric_identifier_is_lower_than_alphanumeric():
    assert compare("1.0.0-1", "1.0.0-a") == -1
    assert compare("1.0.0-99999", "1.0.0-A") == -1
    assert compare("1.0.0-alpha.1", "1.0.0-alpha.beta") == -1
    assert compare("1.0.0-99", "1.0.0-0a") == -1
    assert compare("1.0.0-9", "1.0.0--") == -1


def test_alphanumeric_identifiers_compare_in_ascii_order():
    assert compare("1.0.0-alpha", "1.0.0-beta") == -1
    assert compare("1.0.0-Z", "1.0.0-a") == -1
    assert compare("1.0.0-RC", "1.0.0-rc") == -1
    assert compare("1.0.0-alpha-1", "1.0.0-alpha0") == -1
    assert compare("1.0.0-a-b", "1.0.0-a-c") == -1
    assert compare("1.0.0-abc", "1.0.0-abd") == -1
    assert compare("1.0.0-1a", "1.0.0-1b") == -1
    assert compare("1.0.0-9a", "1.0.0-10a") == 1  # strings, not numbers: "9a" > "10a"


def test_longer_prerelease_wins_when_shared_identifiers_are_equal():
    assert compare("1.0.0-alpha", "1.0.0-alpha.0") == -1
    assert compare("1.0.0-alpha.1", "1.0.0-alpha.1.0") == -1
    assert compare("1.0.0-a.b.c", "1.0.0-a.b") == 1


def test_earlier_identifier_decides_before_length():
    assert compare("1.0.0-a.z", "1.0.0-b") == -1
    assert compare("1.0.0-1.99.99", "1.0.0-2") == -1


def test_equal_prereleases():
    assert compare("1.0.0-alpha.1", "1.0.0-alpha.1") == 0
    assert compare("1.0.0-0", "1.0.0-0") == 0


@pytest.mark.parametrize("a, b", list(itertools.combinations(CHAIN, 2)))
def test_antisymmetry(a, b):
    assert compare(a, b) == -compare(b, a)
