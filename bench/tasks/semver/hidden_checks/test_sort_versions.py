import pytest
from semver import sort_versions


def test_sorts_ascending_numerically():
    assert sort_versions(["1.10.0", "1.2.0", "1.9.0", "0.9.9", "2.0.0"]) == [
        "0.9.9",
        "1.2.0",
        "1.9.0",
        "1.10.0",
        "2.0.0",
    ]


def test_spec_chain_from_shuffled_input():
    chain = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    ]
    shuffled = [chain[i] for i in (5, 0, 7, 3, 6, 1, 4, 2)]
    assert sort_versions(shuffled) == chain


def test_prereleases_mixed_with_releases():
    versions = ["1.0.0", "0.9.0", "1.0.0-rc.1", "1.1.0-alpha", "1.0.1", "1.0.0-2", "1.0.0-a"]
    assert sort_versions(versions) == [
        "0.9.0",
        "1.0.0-2",
        "1.0.0-a",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "1.1.0-alpha",
    ]


def test_input_is_not_mutated_and_result_is_a_new_list():
    original = ["2.0.0", "1.0.0", "1.5.0"]
    snapshot = list(original)
    result = sort_versions(original)
    assert original == snapshot
    assert result is not original
    assert result == ["1.0.0", "1.5.0", "2.0.0"]


def test_already_sorted_input_still_returns_a_new_list():
    original = ["1.0.0", "2.0.0"]
    result = sort_versions(original)
    assert result == original
    assert result is not original


def test_stable_for_equal_precedence():
    versions = ["1.0.0+b", "1.0.0+a", "0.5.0", "1.0.0", "1.0.0+c"]
    assert sort_versions(versions) == ["0.5.0", "1.0.0+b", "1.0.0+a", "1.0.0", "1.0.0+c"]
    reverse_builds = ["1.0.0+c", "1.0.0", "1.0.0+a", "1.0.0+b"]
    assert sort_versions(reverse_builds) == reverse_builds


def test_stable_within_equal_prereleases():
    versions = ["1.0.0-rc.1+z", "1.0.0-rc.1+y", "1.0.0-rc.0+q"]
    assert sort_versions(versions) == ["1.0.0-rc.0+q", "1.0.0-rc.1+z", "1.0.0-rc.1+y"]


def test_returns_original_strings_including_build():
    assert sort_versions(["1.0.0+build.5", "0.1.0+x"]) == ["0.1.0+x", "1.0.0+build.5"]


def test_empty_and_single():
    assert sort_versions([]) == []
    assert sort_versions(["1.2.3"]) == ["1.2.3"]


def test_duplicates_are_kept():
    assert sort_versions(["1.0.0", "1.0.0", "0.1.0"]) == ["0.1.0", "1.0.0", "1.0.0"]


@pytest.mark.parametrize("bad", ["1.2", "v1.0.0", "01.0.0", "1.0.0 ", "", "1.0.0-01"])
def test_invalid_element_raises_value_error(bad):
    with pytest.raises(ValueError):
        sort_versions(["1.0.0", bad, "2.0.0"])


def test_invalid_element_in_single_item_list_raises():
    with pytest.raises(ValueError):
        sort_versions(["not a version"])
    with pytest.raises(ValueError):
        sort_versions([None])
