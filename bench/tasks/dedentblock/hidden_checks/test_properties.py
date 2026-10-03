import random

import pytest
from dedentblock import common_margin, dedent


def random_block(rng):
    lines = []
    for _ in range(rng.randint(0, 6)):
        indent = "".join(rng.choice([" ", "\t"]) for _ in range(rng.randint(0, 5)))
        body = "".join(rng.choice(["a", "b", " ", "\t", "x y"]) for _ in range(rng.randint(0, 4)))
        lines.append(indent + body)
    return "\n".join(lines)


def is_blank(line):
    return line.strip(" \t") == ""


def test_dedent_is_idempotent():
    rng = random.Random(11)
    for _ in range(500):
        text = random_block(rng)
        once = dedent(text)
        assert dedent(once) == once


def test_the_dedented_block_has_no_margin_left():
    rng = random.Random(12)
    for _ in range(500):
        text = random_block(rng)
        assert common_margin(dedent(text)) == ""


def test_every_non_blank_line_started_with_the_margin_and_is_otherwise_kept():
    rng = random.Random(13)
    for _ in range(500):
        text = random_block(rng)
        margin = common_margin(text)
        lines, out = text.split("\n"), dedent(text).split("\n")
        assert len(lines) == len(out)
        for before, after in zip(lines, out, strict=True):
            if is_blank(before):
                assert after == ""
            else:
                assert before == margin + after


def test_the_margin_is_the_longest_common_indentation_prefix():
    rng = random.Random(14)
    for _ in range(500):
        text = random_block(rng)
        margin = common_margin(text)
        lines = [line for line in text.split("\n") if not is_blank(line)]
        assert all(line.startswith(margin) for line in lines)
        if lines:
            # One more character of the first line's indentation would not be shared by all.
            first = lines[0]
            indent = first[: len(first) - len(first.lstrip(" \t"))]
            longer = indent[: len(margin) + 1]
            assert longer == margin or not all(line.startswith(longer) for line in lines)


def test_indenting_a_block_by_a_fixed_prefix_and_dedenting_gives_the_original_dedented():
    rng = random.Random(15)
    for _ in range(300):
        text = random_block(rng)
        prefix = rng.choice(["  ", "\t", "    "])
        indented = "\n".join(
            prefix + line if not is_blank(line) else line for line in text.split("\n")
        )
        assert dedent(indented) == dedent(text)


@pytest.mark.parametrize("bad", [None, 5, b"  a", ["  a"], 2.5])
def test_non_string_argument_raises_value_error(bad):
    with pytest.raises(ValueError):
        common_margin(bad)
    with pytest.raises(ValueError):
        dedent(bad)
