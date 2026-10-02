import pytest
from bytesize import format_size


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (1280, "1.3 KiB"),
        (1331, "1.3 KiB"),
        (1229, "1.2 KiB"),
        (1126, "1.1 KiB"),
        (1127, "1.1 KiB"),
        (1024 * 3 + 512 + 256, "3.8 KiB"),
        (1024**2 * 5 // 4, "1.3 MiB"),
    ],
)
def test_binary_halves_round_up(n, text):
    assert format_size(n) == text


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (1049, "1 KB"),
        (1050, "1.1 KB"),
        (1051, "1.1 KB"),
        (1150, "1.2 KB"),
        (1250, "1.3 KB"),
        (1350, "1.4 KB"),
        (1450, "1.5 KB"),
        (1949, "1.9 KB"),
        (1950, "2 KB"),
        (2050, "2.1 KB"),
        (2_250_000, "2.3 MB"),
    ],
)
def test_decimal_halves_round_up_exactly(n, text):
    # 1.05, 1.15, 1.45 and 1.95 are not exact in binary floating point
    assert format_size(n, binary=False) == text


def test_a_zero_tenth_drops_the_decimal_point():
    assert format_size(1024 * 2 + 10) == "2 KiB"
    assert format_size(3000, binary=False) == "3 KB"
    assert format_size(3049, binary=False) == "3 KB"
    assert format_size(3050, binary=False) == "3.1 KB"


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (1024**2 - 1, "1 MiB"),
        (1048525, "1 MiB"),
        (1048524, "1023.9 KiB"),
        (1024**3 - 1, "1 GiB"),
        (1024**4 - 1, "1 TiB"),
        (1024**5 - 1, "1 PiB"),
        (1023 * 1024, "1023 KiB"),
    ],
)
def test_binary_rounding_up_to_1024_moves_to_the_next_unit(n, text):
    assert format_size(n) == text


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (999_999, "1 MB"),
        (999_950, "1 MB"),
        (999_949, "999.9 KB"),
        (999_999_999, "1 GB"),
        (10**12 - 1, "1 TB"),
        (10**15 - 1, "1 PB"),
        (999_000, "999 KB"),
    ],
)
def test_decimal_rounding_up_to_1000_moves_to_the_next_unit(n, text):
    assert format_size(n, binary=False) == text


def test_the_top_unit_has_no_next_unit_to_move_to():
    assert format_size(1024**5 * 1024 - 1) == "1024 PiB"
    assert format_size(10**18 - 1, binary=False) == "1000 PB"
