import pytest
from bytesize import parse_size


@pytest.mark.parametrize("text", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_empty_or_whitespace_only_is_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize("text", ["KB", "KiB", "B", "K", "MB 1", "b1"])
def test_a_unit_without_a_number_is_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize(
    "text",
    [
        ".5 KB",
        "5. KB",
        "1.5.5 KB",
        "1..5 KB",
        "1,5 KB",
        "1e3 B",
        "1E3",
        "1_000",
        "0x10",
        "1/2 KB",
        "1 000 KB",
        "1 0.5 KB",
        "KB1",
    ],
)
def test_malformed_numbers_are_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize("text", ["-1 KB", "-1", "+1 KB", "+1", "--1", "- 1 KB", "1-1"])
def test_signs_are_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize(
    "text",
    [
        "1 XB",
        "1 Ki",
        "1 KBB",
        "1 KIBB",
        "1 kilobyte",
        "1 bytes",
        "1 byte",
        "1 Kbit",
        "1 EB",
        "1 ZB",
        "1 BB",
        "1 iB",
        "1 KiBs",
        "1 MiBytes",
        "1 PP",
    ],
)
def test_unknown_units_are_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize(
    "text",
    ["1 K B", "1 Ki B", "1 KB KB", "1 KB 2", "1 KB!", "1 KB,", "(1 KB)", "1 KB\x00", "1 KB;"],
)
def test_other_characters_and_extra_text_are_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize("text", ["١ KB", "٣", "１ KB", "1٢ KB", "1.٥ KB", "1 ＫＢ"])
def test_non_ascii_digits_and_letters_are_rejected(text):
    with pytest.raises(ValueError):
        parse_size(text)


@pytest.mark.parametrize("value", [1024, 0, 1.5, None, b"1 KB", ["1 KB"], ("1 KB",), {"1 KB"}])
def test_non_string_input_is_a_type_error(value):
    with pytest.raises(TypeError):
        parse_size(value)


def test_valid_strings_still_parse_after_the_errors():
    assert parse_size("1 KB") == 1000
    assert parse_size("512") == 512
