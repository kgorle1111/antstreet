import pytest
from isoweek import parse_iso_week


@pytest.mark.parametrize("text", ["2021-W53-1", "2019-W53-7", "2023-W53-1", "2014-W53-3"])
def test_week_53_is_rejected_in_a_short_year(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize("text", ["2020-W54-1", "2020-W99-1", "2024-W60-3", "2020-W00-1"])
def test_a_week_out_of_range_is_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize("text", ["2020-W01-0", "2020-W01-8", "2020-W01-9", "2024-W11-0"])
def test_a_weekday_out_of_range_is_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize("text", ["0000-W01-1", "0000-W52-7"])
def test_year_zero_is_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize("text", ["9999-W52-7", "9999-W52-6", "9999-W53-1"])
def test_a_date_beyond_the_range_of_date_is_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "2020",
        "2020-W01",
        "2020W011",
        "2020-W1-1",
        "2020-W001-1",
        "20-W01-1",
        "020-W01-1",
        "02020-W01-1",
        "2020-w01-1",
        "2020-01-01",
        "2020-W01-11",
        "2020-W01-",
        "2020-W-1-1",
        "2020_W01_1",
        "2020 W01 1",
        "-2020-W01-1",
        "+020-W01-1",
        "2020-W+1-1",
        "2020-W01-+1",
        "2020-W01-1-",
        "W01-1",
    ],
)
def test_text_that_does_not_match_the_format_is_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize(
    "text",
    [" 2020-W01-1", "2020-W01-1 ", "2020-W01-1\n", "\t2020-W01-1", "2020 -W01-1", "2020-W01 -1"],
)
def test_whitespace_is_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


@pytest.mark.parametrize(
    "text",
    ["٢٠٢٠-W01-1", "2020-W٠١-1", "2020-W01-١", "２０２０-W01-1", "2020-W01-１", "2020-W０1-1"],
)
def test_non_ascii_digits_are_rejected(text):
    with pytest.raises(ValueError):
        parse_iso_week(text)


def test_valid_text_still_parses_after_the_errors():
    assert parse_iso_week("2024-W11-5").isoformat() == "2024-03-15"
