import pytest
from rlecodec import encode


@pytest.mark.parametrize(
    ("text", "encoded"),
    [
        ("", ""),
        ("a", "1a"),
        ("aa", "2a"),
        ("aaabcc", "3a1b2c"),
        ("abc", "1a1b1c"),
        ("abcabc", "1a1b1c1a1b1c"),
        ("aabbaa", "2a2b2a"),
        (
            "WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWBWWWWWWWWWWWWWW",
            "12W1B12W3B24W1B14W",
        ),
        ("x" * 9, "9x"),
        ("x" * 10, "10x"),
        ("x" * 123, "123x"),
        ("x" * 1000, "1000x"),
        (" ", "1 "),
        ("   ", "3 "),
        ("a b", "1a1 1b"),
        ("a.b.", "1a1.1b1."),
    ],
)
def test_known_encodings(text, encoded):
    assert encode(text) == encoded


def test_a_long_run_has_a_single_token():
    assert encode("z" * 100000) == "100000z"
    assert encode("z" * 99999 + "y") == "99999z1y"


def test_a_run_is_maximal_so_equal_neighbours_are_never_split():
    assert encode("aaaa") == "4a"
    assert encode("aaaab") == "4a1b"
    assert encode("baaaa") == "1b4a"
    assert encode("a" + "b" * 5 + "a") == "1a5b1a"


def test_case_matters():
    assert encode("aA") == "1a1A"
    assert encode("AAaa") == "2A2a"


def test_line_breaks_and_tabs_are_ordinary_characters():
    assert encode("a\n\n\nb") == "1a3\n1b"
    assert encode("\t\t") == "2\t"
    assert encode("\r\n") == "1\r1\n"


def test_characters_of_any_script_are_written_as_they_are():
    assert encode("\u00e9\u00e9\u00e9") == "3\u00e9"
    assert encode("\u4e2d\u4e2d") == "2\u4e2d"
    assert encode("\u0663\u0663") == "2\u0663"  # an Arabic-Indic digit is not an ASCII digit
    assert encode("\uff11") == "1\uff11"  # nor is a full-width one
    assert encode("\U0001f600" * 4) == "4\U0001f600"


def test_the_result_is_a_str():
    assert type(encode("")) is str
    assert type(encode("aab")) is str
