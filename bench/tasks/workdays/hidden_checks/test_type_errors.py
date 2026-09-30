from datetime import date, datetime

import pytest
from workdays import add_business_days, add_months, business_days_between

D = date(2024, 1, 15)
DT = datetime(2024, 1, 15, 9, 30)
NOT_DATES = [DT, "2024-01-15", None, 20240115, 1.5, (2024, 1, 15)]
NOT_INTS = [1.5, "1", None, 2.0, [1]]


@pytest.mark.parametrize("bad", NOT_DATES)
def test_add_months_rejects_a_non_date(bad):
    with pytest.raises(TypeError):
        add_months(bad, 1)


@pytest.mark.parametrize("bad", NOT_INTS)
def test_add_months_rejects_a_non_int_months(bad):
    with pytest.raises(TypeError):
        add_months(D, bad)


@pytest.mark.parametrize("bad", NOT_DATES)
def test_business_days_between_rejects_a_non_date_start(bad):
    with pytest.raises(TypeError):
        business_days_between(bad, D)


@pytest.mark.parametrize("bad", NOT_DATES)
def test_business_days_between_rejects_a_non_date_end(bad):
    with pytest.raises(TypeError):
        business_days_between(D, bad)


def test_business_days_between_rejects_a_datetime_even_when_the_range_is_empty():
    with pytest.raises(TypeError):
        business_days_between(DT, DT)
    with pytest.raises(TypeError):
        business_days_between(DT, D)
    with pytest.raises(TypeError):
        business_days_between(D, DT)


@pytest.mark.parametrize("bad", NOT_DATES)
def test_add_business_days_rejects_a_non_date(bad):
    with pytest.raises(TypeError):
        add_business_days(bad, 1)


def test_add_business_days_rejects_a_datetime_even_when_n_is_zero():
    with pytest.raises(TypeError):
        add_business_days(DT, 0)
    with pytest.raises(TypeError):
        add_business_days(DT, -1)


@pytest.mark.parametrize("bad", NOT_INTS)
def test_add_business_days_rejects_a_non_int_n(bad):
    with pytest.raises(TypeError):
        add_business_days(D, bad)


def test_valid_arguments_are_still_accepted():
    assert add_months(D, 1) == date(2024, 2, 15)
    assert business_days_between(D, date(2024, 1, 16)) == 1
    assert add_business_days(D, 1) == date(2024, 1, 16)
