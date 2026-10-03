import random

import pytest
from urlquery import build_query, parse_query

TRICKY = [
    {"a": ["1"]},
    {"a": [""]},
    {"a": ["", ""]},
    {"a b": ["c d", "e+f"]},
    {"a&b=c": ["x&y=z", "%41", "%"]},
    {"é": ["€", "\U0001f600"], "k": ["~-._"]},
    {"?": ["?"], "#": ["#"]},
    {"\n": ["\t", "\r\n"]},
    {"z": ["1", "2"], "a": ["3"], "m": ["4", "5", "6"]},
]


@pytest.mark.parametrize("params", TRICKY)
def test_roundtrip_of_hand_picked_dicts(params):
    assert parse_query(build_query(params)) == params


def test_roundtrip_keeps_key_order():
    params = {"z": ["1"], "a": ["2"], "m": ["3"]}
    assert list(parse_query(build_query(params))) == ["z", "a", "m"]


def test_roundtrip_of_random_dicts():
    rng = random.Random(3986)
    alphabet = ["a", "Z", "0", " ", "&", "=", "+", "%", "?", "é", "€", "~", "/", "\n"]
    for _ in range(300):
        params = {}
        for _ in range(rng.randint(0, 4)):
            key = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 5)))
            params[key] = [
                "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 5)))
                for _ in range(rng.randint(1, 3))
            ]
        assert parse_query(build_query(params)) == params


def test_a_bare_string_value_roundtrips_as_a_one_item_list():
    assert parse_query(build_query({"a": "x y"})) == {"a": ["x y"]}
