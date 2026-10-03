import pytest
from bytesize import parse_size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("1.5 KiB", 1536),
        ("1.5KiB", 1536),
        ("2.5 MB", 2_500_000),
        ("0.5 KiB", 512),
        ("0.25 MiB", 262144),
        ("1.25 KB", 1250),
        ("0.001 KB", 1),
        ("10.0 B", 10),
        ("1.5 K", 1536),
    ],
)
def test_decimal_numbers(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("0.5 B", 1),
        ("1.5 B", 2),
        ("2.5 B", 3),
        ("3.5 B", 4),
        ("0.4 B", 0),
        ("0.49 B", 0),
        ("1.5", 2),
        ("0.1 KiB", 102),
        ("0.3 KiB", 307),
        ("0.01 KiB", 10),
        ("0.0005 KB", 1),
        ("0.0004 KB", 0),
        ("1.0005 KB", 1001),
        ("1.0004 KB", 1000),
        ("1.0006 KB", 1001),
    ],
)
def test_rounding_to_the_nearest_byte_with_halves_up(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("9007199254740993", 9007199254740993),
        ("9007199254740993 B", 9007199254740993),
        ("123456789.123456789 GB", 123456789123456789),
        ("1234567890123456789012", 1234567890123456789012),
        ("9007199254740993 KB", 9007199254740993000),
        ("4503599627370497.5", 4503599627370498),
        ("0.1 PB", 10**14),
        ("1.000000000000001 PB", 1000000000000001),
    ],
)
def test_large_values_are_exact(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    "text",
    ["  1 KB", "1 KB  ", "\t1 KB\n", "  1 KB  ", "\n\n512\n", " 1.5 KiB "],
)
def test_whitespace_around_the_text(text):
    assert parse_size(text) in {1000, 512, 1536}


@pytest.mark.parametrize("text", ["1 KB", "1KB", "1  KB", "1\tKB", "1 \t KB", "1     KB"])
def test_spaces_and_tabs_between_number_and_unit(text):
    assert parse_size(text) == 1000
