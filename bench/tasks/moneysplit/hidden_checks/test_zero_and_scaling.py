import pytest
from moneysplit import split_by_ratio


@pytest.mark.parametrize(
    ("total", "ratios", "shares"),
    [
        (10, [0, 1], [0, 10]),
        (10, [1, 0, 1], [5, 0, 5]),
        (7, [0, 1, 0, 1], [0, 4, 0, 3]),
        (3, [0, 0, 5], [0, 0, 3]),
        (100, [5], [100]),
        (0, [0, 3], [0, 0]),
        (1, [0, 1, 1], [0, 1, 0]),
    ],
)
def test_a_zero_ratio_always_gets_zero(total, ratios, shares):
    assert split_by_ratio(total, ratios) == shares


@pytest.mark.parametrize("ratios", [[1, 2], [1, 1, 1], [3, 2, 1], [0, 1, 4, 2], [7]])
@pytest.mark.parametrize("factor", [2, 3, 10, 1000])
def test_scaling_all_ratios_changes_nothing(ratios, factor):
    scaled = [r * factor for r in ratios]
    for total in (0, 1, 2, 7, 10, 99, 100, 12345):
        assert split_by_ratio(total, scaled) == split_by_ratio(total, ratios)


def test_split_even_matches_equal_ratios():
    from moneysplit import split_even

    for total in range(0, 60):
        for parts in range(1, 9):
            assert split_even(total, parts) == split_by_ratio(total, [1] * parts)
            assert split_even(total, parts) == split_by_ratio(total, [5] * parts)


def test_a_generator_is_read_once_and_still_gives_the_right_answer():
    ratios = (r for r in [1, 2, 3])
    assert split_by_ratio(100, ratios) == [17, 33, 50]
