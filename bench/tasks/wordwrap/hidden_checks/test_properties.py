import random

from wordwrap import wrap


def random_text(rng, max_word):
    pieces = []
    for _ in range(rng.randint(0, 25)):
        pieces.append("x" * rng.randint(1, max_word))
        pieces.append(rng.choice([" ", "  ", "\n", " \t "]))
    return "".join(pieces)


def test_no_line_is_longer_than_width_or_empty():
    rng = random.Random(72)
    for _ in range(300):
        width = rng.randint(4, 20)
        first, rest = rng.choice(["", "- ", "  "]), rng.choice(["", "  ", "> "])
        for line in wrap(random_text(rng, 30), width, first, rest):
            assert 0 < len(line) <= width


def test_lines_start_with_their_indent_and_never_end_with_a_space():
    rng = random.Random(73)
    for _ in range(200):
        first, rest = rng.choice(["* ", "   "]), rng.choice(["", ". "])
        lines = wrap(random_text(rng, 8), 12, first, rest)
        for number, line in enumerate(lines):
            assert line.startswith(first if number == 0 else rest)
            assert not line.endswith(" ")


def test_when_no_word_is_cut_the_words_come_back_in_order():
    rng = random.Random(74)
    for _ in range(300):
        width = rng.randint(10, 25)
        text = random_text(rng, 7)
        lines = wrap(text, width, "ab ", "cd ")
        words = []
        for line in lines:
            words += line[3:].split(" ")
        assert words == text.split()


def test_every_character_of_the_text_is_kept_when_words_are_cut():
    rng = random.Random(75)
    for _ in range(300):
        width = rng.randint(3, 9)
        text = random_text(rng, 20)
        lines = wrap(text, width)
        assert "".join(lines).replace(" ", "") == "".join(text.split())


def test_wrapping_wrapped_text_changes_nothing():
    rng = random.Random(76)
    for _ in range(200):
        width = rng.randint(3, 15)
        once = wrap(random_text(rng, 20), width)
        assert wrap("\n".join(once), width) == once
