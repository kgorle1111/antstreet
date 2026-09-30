import random
import re

from justify import justify


def _cases():
    rng = random.Random(20260930)
    for _ in range(200):
        words = [
            "".join(rng.choice("abcdefgh") for _ in range(rng.randint(1, 9)))
            for _ in range(rng.randint(1, 30))
        ]
        width = max(map(len, words)) + rng.randint(0, 15)
        yield " ".join(words), width


def test_every_line_is_exactly_width_and_words_survive():
    for text, width in _cases():
        lines = justify(text, width)
        assert all(len(line) == width for line in lines)
        assert " ".join(lines).split() == text.split()


def test_lines_are_greedy():
    for text, width in _cases():
        lines = justify(text, width)
        for line, following in zip(lines, lines[1:], strict=False):
            words = line.split()
            first_of_next = following.split()[0]
            assert len(" ".join(words)) + 1 + len(first_of_next) > width


def test_gaps_are_at_least_one_and_differ_by_at_most_one_leftmost_widest():
    for text, width in _cases():
        for line in justify(text, width)[:-1]:
            words = line.split()
            if len(words) == 1:
                assert line == words[0].ljust(width)
                continue
            assert line == line.strip()
            gaps = [len(g) for g in re.findall(r" +", line)]
            assert len(gaps) == len(words) - 1
            assert min(gaps) >= 1
            assert max(gaps) - min(gaps) <= 1
            assert gaps == sorted(gaps, reverse=True)
