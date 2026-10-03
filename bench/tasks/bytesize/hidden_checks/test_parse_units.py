import pytest
from bytesize import parse_size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("1 KB", 1000),
        ("1 MB", 1000**2),
        ("1 GB", 1000**3),
        ("1 TB", 1000**4),
        ("1 PB", 1000**5),
        ("2 KB", 2000),
        ("10 MB", 10_000_000),
    ],
)
def test_decimal_units(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("1 KiB", 1024),
        ("1 MiB", 1024**2),
        ("1 GiB", 1024**3),
        ("1 TiB", 1024**4),
        ("1 PiB", 1024**5),
        ("2 KiB", 2048),
        ("8 PiB", 2**53),
    ],
)
def test_binary_units(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("1K", 1024),
        ("1M", 1024**2),
        ("1G", 1024**3),
        ("1T", 1024**4),
        ("1P", 1024**5),
        ("3 K", 3072),
    ],
)
def test_single_letters_are_the_binary_units(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("1 B", 1),
        ("512", 512),
        ("512 B", 512),
        ("0", 0),
        ("0 B", 0),
        ("0 KiB", 0),
        ("007 KB", 7000),
        ("1b", 1),
    ],
)
def test_bytes_and_no_unit(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("1 kb", 1000),
        ("1 Kb", 1000),
        ("1 kB", 1000),
        ("1 KB", 1000),
        ("1 kib", 1024),
        ("1 KIB", 1024),
        ("1 kIb", 1024),
        ("1 mib", 1024**2),
        ("1 gb", 1000**3),
        ("1 k", 1024),
        ("1 p", 1024**5),
        ("10 gib", 10 * 1024**3),
        ("1 b", 1),
    ],
)
def test_units_are_case_insensitive(text, size):
    assert parse_size(text) == size


def test_the_two_families_differ():
    assert parse_size("1 KB") != parse_size("1 KiB")
    assert parse_size("1 K") == parse_size("1 KiB")
    assert parse_size("1 Mb") == parse_size("1 MB") == 1_000_000
    assert parse_size("1 MiB") == 1_048_576


def test_result_is_an_int():
    for text in ("1", "1 KB", "1.5 KiB", "0", "0.5 B"):
        assert type(parse_size(text)) is int
