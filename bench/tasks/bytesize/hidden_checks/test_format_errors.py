import pytest
from bytesize import format_size, parse_size


@pytest.mark.parametrize("n", [-1, -1024, -(10**30)])
def test_negative_values_are_rejected(n):
    with pytest.raises(ValueError):
        format_size(n)
    with pytest.raises(ValueError):
        format_size(n, binary=False)


@pytest.mark.parametrize("n", [1.5, 1024.0, 0.0, "1024", None, True, False, [1024], b"1"])
def test_values_that_are_not_ints_are_type_errors(n):
    with pytest.raises(TypeError):
        format_size(n)
    with pytest.raises(TypeError):
        format_size(n, binary=False)


def test_valid_calls_still_work_after_the_errors():
    assert format_size(2048) == "2 KiB"
    assert format_size(2000, binary=False) == "2 KB"


@pytest.mark.parametrize("text", ["1.5 KiB", "2 KiB", "1 MiB", "10 KiB", "5.5 MiB", "512 B", "0 B"])
def test_formatting_a_parsed_size_gives_back_the_text(text):
    assert format_size(parse_size(text)) == text


@pytest.mark.parametrize("text", ["1.5 KB", "2 KB", "1 MB", "10 KB", "999 B", "2.5 GB"])
def test_formatting_a_parsed_decimal_size_gives_back_the_text(text):
    assert format_size(parse_size(text), binary=False) == text
