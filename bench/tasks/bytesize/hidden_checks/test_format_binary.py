import pytest
from bytesize import format_size


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0 B"),
        (1, "1 B"),
        (512, "512 B"),
        (1000, "1000 B"),
        (1023, "1023 B"),
        (1024, "1 KiB"),
        (1025, "1 KiB"),
        (1100, "1.1 KiB"),
        (1536, "1.5 KiB"),
        (2048, "2 KiB"),
        (10 * 1024, "10 KiB"),
        (1_000_000, "976.6 KiB"),
        (1024**2, "1 MiB"),
        (5 * 1024**2 + 512 * 1024, "5.5 MiB"),
        (1024**3, "1 GiB"),
        (1024**4, "1 TiB"),
        (1024**5, "1 PiB"),
    ],
)
def test_binary_is_the_default(n, text):
    assert format_size(n) == text
    assert format_size(n, True) == text
    assert format_size(n, binary=True) == text


@pytest.mark.parametrize(
    ("n", "text"),
    [(1024**6, "1024 PiB"), (3 * 1024**6, "3072 PiB"), (1024**5 * 5 // 2, "2.5 PiB")],
)
def test_there_is_no_unit_above_pib(n, text):
    assert format_size(n) == text


def test_zero_is_zero_bytes_and_bytes_have_no_decimal():
    assert format_size(0) == "0 B"
    for n in (1, 7, 100, 999, 1023):
        assert format_size(n) == f"{n} B"
    for n in (1, 7, 100, 999):
        assert format_size(n, binary=False) == f"{n} B"


def test_the_unit_is_the_largest_one_that_fits():
    assert format_size(1023 * 1024) == "1023 KiB"
    assert format_size(1024 * 1024) == "1 MiB"
    assert format_size(1024**3 * 3 // 2) == "1.5 GiB"
    assert format_size(1024**4 * 7) == "7 TiB"


def test_huge_values_are_exact():
    assert format_size(10**40) == "8881784197001252323389053.3 PiB"
    assert format_size(2**200) == f"{2**150} PiB"


def test_result_is_a_str_with_one_space():
    for n in (0, 1, 1536, 1024**3):
        text = format_size(n)
        assert isinstance(text, str)
        assert text.count(" ") == 1
