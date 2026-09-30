import random

import pytest
from csvline import format_line, parse_line

TRICKY = [
    [""],
    ["", ""],
    ["", "", ""],
    [" "],
    ["a", ""],
    ['"'],
    ['""'],
    ['"a"'],
    ['a"b', 'c""d'],
    ["a,b", "c"],
    [","],
    ["\n"],
    ["\r"],
    ["\r\n"],
    ["a\r\nb\nc\rd"],
    [" lead", "trail ", " both ", "in ner"],
    ["\t", "\ta", "b\t"],
    ['line one\nline "two", three\n'],
    ['""\n,"'],
    ["x", "y", "z"],
]


@pytest.mark.parametrize("fields", TRICKY)
def test_roundtrip_of_hand_picked_records(fields):
    assert parse_line(format_line(fields)) == fields


def test_roundtrip_of_random_records():
    rng = random.Random(4180)
    alphabet = ["a", "b", " ", ",", '"', "\n", "\r", "\t", "é"]
    for _ in range(500):
        fields = [
            "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
            for _ in range(rng.randint(1, 5))
        ]
        assert parse_line(format_line(fields)) == fields


def test_parse_then_format_keeps_ordinary_records():
    for line in ["a,b,c", 'a,"b,c",d', '"say ""hi"""', ",", ""]:
        assert format_line(parse_line(line)) == line
