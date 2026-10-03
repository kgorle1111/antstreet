import pytest
from contfrac import best_approximation, continued_fraction, convergents, from_continued_fraction

BAD_INTS = [1.0, 2.5, "3", None, True, False, [3], 1 + 0j]


@pytest.mark.parametrize("bad", BAD_INTS)
def test_a_number_that_is_not_an_int_raises_type_error(bad):
    with pytest.raises(TypeError):
        continued_fraction(bad, 3)
    with pytest.raises(TypeError):
        continued_fraction(3, bad)
    with pytest.raises(TypeError):
        best_approximation(bad, 3, 5)
    with pytest.raises(TypeError):
        best_approximation(3, bad, 5)
    with pytest.raises(TypeError):
        best_approximation(3, 4, bad)


@pytest.mark.parametrize("bad", [None, 5, "123", {1: 2}, {1, 2}, 1.5])
def test_terms_that_are_not_a_list_raise_type_error(bad):
    with pytest.raises(TypeError):
        from_continued_fraction(bad)
    with pytest.raises(TypeError):
        convergents(bad)


@pytest.mark.parametrize("bad", BAD_INTS)
def test_a_term_that_is_not_an_int_raises_type_error(bad):
    for position in (0, 1, 2):
        terms = [1, 2, 3]
        terms[position] = bad
        with pytest.raises(TypeError):
            from_continued_fraction(terms)
        with pytest.raises(TypeError):
            convergents(terms)


def test_empty_terms_raise_value_error():
    with pytest.raises(ValueError):
        from_continued_fraction([])
    with pytest.raises(ValueError):
        convergents([])
    with pytest.raises(ValueError):
        convergents(())


@pytest.mark.parametrize("bad", [0, -1, -7])
def test_a_term_after_the_first_below_one_raises_value_error(bad):
    for position in (1, 2, 3):
        terms = [4, 2, 6, 7]
        terms[position] = bad
        with pytest.raises(ValueError):
            from_continued_fraction(terms)
        with pytest.raises(ValueError):
            convergents(terms)


@pytest.mark.parametrize("first", [0, -1, -50, 12])
def test_the_first_term_may_be_any_int(first):
    assert from_continued_fraction([first, 2]) == (2 * first + 1, 2)
    assert convergents([first, 2]) == [(first, 1), (2 * first + 1, 2)]


def test_a_zero_denominator_raises_value_error():
    for n in (0, 1, -5):
        with pytest.raises(ValueError):
            continued_fraction(n, 0)
        with pytest.raises(ValueError):
            best_approximation(n, 0, 5)


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_a_limit_below_one_raises_value_error(limit):
    with pytest.raises(ValueError):
        best_approximation(1, 3, limit)
    with pytest.raises(ValueError):
        best_approximation(1, 1, limit)
