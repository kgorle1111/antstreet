import random

from cidr4 import contains, parse_cidr, summarise

BASE = 0x0A000000  # 10.0.0.0; the random blocks all live in 10.0.0.0/24


def ip_text(n):
    return f"{n >> 24}.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def block(offset, prefix):
    return f"{ip_text(BASE + offset)}/{prefix}"


def addresses(blocks):
    covered = set()
    for text in blocks:
        start, prefix = parse_cidr(text)
        covered.update(range(start, start + 2 ** (32 - prefix)))
    return covered


def random_blocks(rng):
    out = []
    for _ in range(rng.randrange(0, 9)):
        prefix = rng.randrange(24, 33)
        size = 2 ** (32 - prefix)
        out.append(block(rng.randrange(0, 256 // size) * size, prefix))
    return out


def test_the_summary_covers_exactly_the_same_addresses():
    rng = random.Random(4242)
    for _ in range(300):
        blocks = random_blocks(rng)
        assert addresses(summarise(blocks)) == addresses(blocks), blocks


def test_the_summary_blocks_do_not_overlap_and_are_ordered_by_address():
    rng = random.Random(777)
    for _ in range(300):
        out = summarise(random_blocks(rng))
        spans = []
        for text in out:
            start, prefix = parse_cidr(text)
            spans.append((start, start + 2 ** (32 - prefix) - 1))
        assert spans == sorted(spans), out
        for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
            assert end < start, out


def test_no_two_blocks_of_the_summary_could_still_merge():
    rng = random.Random(9001)
    for _ in range(300):
        out = [parse_cidr(t) for t in summarise(random_blocks(rng))]
        for (a, pa), (b, pb) in zip(out, out[1:], strict=False):
            halves = pa == pb and a + 2 ** (32 - pa) == b and a % 2 ** (33 - pa) == 0
            assert not halves, out


def test_the_summary_is_never_longer_than_the_input_and_is_stable():
    rng = random.Random(31337)
    for _ in range(300):
        blocks = random_blocks(rng)
        out = summarise(blocks)
        assert len(out) <= len(blocks)
        assert summarise(out) == out
        assert summarise(list(reversed(blocks))) == out


def test_every_address_of_the_input_is_in_some_summary_block():
    rng = random.Random(5)
    for _ in range(100):
        blocks = random_blocks(rng)
        out = summarise(blocks)
        for n in range(0, 256):
            ip = ip_text(BASE + n)
            assert any(contains(b, ip) for b in blocks) == any(contains(b, ip) for b in out)


def test_filling_the_whole_slash_24_one_address_at_a_time_gives_one_block():
    ips = [f"10.0.0.{n}/32" for n in range(256)]
    assert summarise(ips) == ["10.0.0.0/24"]
    assert summarise(list(reversed(ips))) == ["10.0.0.0/24"]
    rng = random.Random(1)
    rng.shuffle(ips)
    assert summarise(ips) == ["10.0.0.0/24"]
