import pytest
from bytesize import format_size


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (1000, "1 KB"),
        (1024, "1 KB"),
        (1500, "1.5 KB"),
        (1536, "1.5 KB"),
        (10_000, "10 KB"),
        (1_000_000, "1 MB"),
        (1_234_567, "1.2 MB"),
        (2_500_000_000, "2.5 GB"),
        (10**12, "1 TB"),
        (10**15, "1 PB"),
        (10**18, "1000 PB"),
        (7 * 10**17, "700 PB"),
    ],
)
def test_decimal_units(n, text):
    assert format_size(n, binary=False) == text
    assert format_size(n, False) == text


def test_the_step_is_1000_not_1024():
    assert format_size(1000, binary=False) == "1 KB"
    assert format_size(1000, binary=True) == "1000 B"
    assert format_size(1024, binary=False) == "1 KB"
    assert format_size(10**6, binary=False) == "1 MB"
    assert format_size(10**6, binary=True) == "976.6 KiB"


def test_unit_names_use_capital_letters_and_no_i():
    names = {format_size(10**e, binary=False).split()[1] for e in range(0, 16, 3)}
    assert names == {"B", "KB", "MB", "GB", "TB", "PB"}
    names = {format_size(1024**e).split()[1] for e in range(0, 6)}
    assert names == {"B", "KiB", "MiB", "GiB", "TiB", "PiB"}


def test_huge_values_are_exact():
    assert format_size(10**40, binary=False) == "10000000000000000000000000 PB"
    assert format_size(10**40 + 5 * 10**14, binary=False) == "10000000000000000000000000.5 PB"
