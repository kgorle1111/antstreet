import pytest
from intervalsched import max_overlap, select_max

BOTH = [select_max, max_overlap]


@pytest.mark.parametrize("fn", BOTH)
@pytest.mark.parametrize("bad", [(2, 2), (3, 1), (0, -1), (1.5, 1.5), (2, 1.9999)])
def test_an_empty_or_backwards_interval_is_a_value_error(fn, bad):
    with pytest.raises(ValueError):
        fn([bad])
    with pytest.raises(ValueError):
        fn([(0, 1), bad, (5, 6)])


@pytest.mark.parametrize("fn", BOTH)
@pytest.mark.parametrize("bad", [(1,), (1, 2, 3), (), 5, "ab", None, {1, 2}, {1: 2, 3: 4}])
def test_an_item_that_is_not_a_pair_is_a_value_error(fn, bad):
    with pytest.raises(ValueError):
        fn([bad])


@pytest.mark.parametrize("fn", BOTH)
@pytest.mark.parametrize("bad", [(True, 2), (0, True), ("a", 2), (1, "b"), (None, 2), (1, None)])
def test_ends_that_are_not_numbers_are_a_type_error(fn, bad):
    with pytest.raises(TypeError):
        fn([bad])


@pytest.mark.parametrize("fn", BOTH)
@pytest.mark.parametrize("bad", [None, 5, "abc", {(1, 2): 1}, {(1, 2)}])
def test_intervals_must_be_a_list_or_tuple(fn, bad):
    with pytest.raises(TypeError):
        fn(bad)


@pytest.mark.parametrize("fn", BOTH)
def test_every_interval_is_checked_even_one_that_would_be_skipped(fn):
    with pytest.raises(ValueError):
        fn([(0, 10), (2, 2)])
    with pytest.raises(ValueError):
        fn([(0, 1), (0, 10), (5, 4)])
    with pytest.raises(TypeError):
        fn([(0, 1), (0, 10), ("x", 4)])


@pytest.mark.parametrize("fn", BOTH)
def test_the_first_bad_item_decides_and_the_shape_comes_before_the_types(fn):
    with pytest.raises(ValueError):
        fn([(3, 1), ("a", 2)])
    with pytest.raises(TypeError):
        fn([("a", 2), (3, 1)])
    with pytest.raises(ValueError):
        fn([("a", 2, 3), (5, 6)])
    with pytest.raises(TypeError):
        fn([("b", 1)])  # types are checked before the order of the ends


@pytest.mark.parametrize("fn", BOTH)
def test_a_tuple_of_pairs_and_lists_as_pairs_are_accepted(fn):
    fn(((1, 2), (3, 4)))
    fn([[1, 2], [3, 4]])
