import random

from editdistance import edit_distance, edit_script


def replay(a, script):
    """Apply a script to a, checking every operation against the characters it claims."""
    i, out = 0, []
    for op in script:
        kind = op[0]
        if kind == "keep":
            assert len(op) == 2 and i < len(a) and a[i] == op[1]
            out.append(op[1])
            i += 1
        elif kind == "sub":
            assert len(op) == 3 and i < len(a) and a[i] == op[1] and op[1] != op[2]
            out.append(op[2])
            i += 1
        elif kind == "delete":
            assert len(op) == 2 and i < len(a) and a[i] == op[1]
            i += 1
        else:
            assert kind == "insert" and len(op) == 2
            out.append(op[1])
    assert i == len(a)
    return "".join(out)


def test_random_scripts_replay_to_b_at_the_distance():
    rng = random.Random(7)
    for _ in range(300):
        a = "".join(rng.choice("abc") for _ in range(rng.randint(0, 12)))
        b = "".join(rng.choice("abc") for _ in range(rng.randint(0, 12)))
        script = edit_script(a, b)
        assert replay(a, script) == b
        assert sum(op[0] != "keep" for op in script) == edit_distance(a, b)


def test_longer_random_strings_over_a_wider_alphabet():
    rng = random.Random(11)
    for _ in range(40):
        a = "".join(rng.choice("abcdefgh") for _ in range(rng.randint(30, 80)))
        b = "".join(rng.choice("abcdefgh") for _ in range(rng.randint(30, 80)))
        script = edit_script(a, b)
        assert replay(a, script) == b
        assert sum(op[0] != "keep" for op in script) == edit_distance(a, b)


def test_distance_properties():
    rng = random.Random(3)
    for _ in range(200):
        a, b, c = ("".join(rng.choice("ab") for _ in range(rng.randint(0, 9))) for _ in range(3))
        d = edit_distance(a, b)
        assert d == edit_distance(b, a)
        assert abs(len(a) - len(b)) <= d <= max(len(a), len(b))
        assert (d == 0) == (a == b)
        assert edit_distance(a, c) <= d + edit_distance(b, c)
