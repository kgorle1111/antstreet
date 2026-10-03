import random

import pytest
from rlecodec import decode, encode


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a",
        "aaabcc",
        "1",
        "\\",
        "1\\1\\",
        "0123456789",
        "9876543210" * 3,
        "\\\\\\\\1111aaaa",
        "a\nb\r\nc\td",
        "\u00e9\u00e9\u0663\u0663\uff11\uff11",
        "\U0001f600\U0001f600x",
        "x" * 5000,
        "ab" * 500,
        "1" * 100 + "\\" * 100 + "a" * 100,
    ],
)
def test_known_texts_round_trip(text):
    assert decode(encode(text)) == text


def test_random_texts_over_a_hostile_alphabet_round_trip():
    rng = random.Random(2026)
    alphabet = ["0", "1", "9", "\\", "a", "b", " ", "\n", "\u0663", "\u00e9"]
    for _ in range(1500):
        text = "".join(
            rng.choice(alphabet) * rng.randrange(1, 6) for _ in range(rng.randrange(0, 20))
        )
        assert decode(encode(text)) == text, text


def test_random_texts_over_all_of_ascii_round_trip():
    rng = random.Random(99)
    for _ in range(500):
        text = "".join(chr(rng.randrange(0, 128)) for _ in range(rng.randrange(0, 60)))
        assert decode(encode(text)) == text


def test_the_encoding_of_a_run_is_shorter_than_the_run_when_it_is_long():
    assert len(encode("a" * 1000)) == 5
    assert len(encode("1" * 1000)) == 6
    assert len(encode("\\" * 1000)) == 6


def test_encode_is_deterministic_and_never_splits_a_run():
    for text in ("aab", "1122", "\\\\a", "xyzzy"):
        assert encode(text) == encode(text)
        assert decode(encode(text)) == text
    assert encode("aaaa") == "4a"


def test_a_limit_just_big_enough_round_trips():
    text = "a" * 777 + "1" * 20
    assert decode(encode(text), len(text)) == text
    with pytest.raises(ValueError):
        decode(encode(text), len(text) - 1)
