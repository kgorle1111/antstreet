import random
from fractions import Fraction

from baseconv import convert, parse_number

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def digits_of(n, base):
    out = ""
    while n:
        n, d = divmod(n, base)
        out = DIGITS[d] + out
    return out or "0"


def expected_text(value, base, max_frac):
    """Cut the value off after max_frac digits with one floor, not digit by digit."""
    size = abs(value)
    scaled = (size.numerator * base**max_frac) // size.denominator
    whole, frac = divmod(scaled, base**max_frac)
    frac_text = digits_of(frac, base).rjust(max_frac, "0") if max_frac else ""
    frac_text = frac_text.rstrip("0")
    text = digits_of(whole, base) + ("." + frac_text if frac_text else "")
    return "-" + text if value < 0 and (whole or frac_text) else text


def random_text(rng, base):
    whole = "".join(rng.choice(DIGITS[:base]) for _ in range(rng.randint(1, 8)))
    text = whole
    if rng.random() < 0.7:
        text += "." + "".join(rng.choice(DIGITS[:base]) for _ in range(rng.randint(1, 8)))
    if rng.random() < 0.3:
        text = "-" + text
    if rng.random() < 0.3:
        text = "".join(ch.upper() for ch in text)
    return text


def test_random_numbers_against_a_single_floor_division():
    rng = random.Random(1234)
    for _ in range(600):
        src, dst = rng.randint(2, 36), rng.randint(2, 36)
        text = random_text(rng, src)
        max_frac = rng.choice([0, 1, 2, 5, 10, 17])
        value = parse_number(text, src)
        assert convert(text, src, dst, max_frac) == expected_text(value, dst, max_frac), (
            text,
            src,
            dst,
            max_frac,
        )


def test_default_max_frac_is_ten():
    rng = random.Random(55)
    for _ in range(200):
        src, dst = rng.randint(2, 36), rng.randint(2, 36)
        text = random_text(rng, src)
        assert convert(text, src, dst) == expected_text(parse_number(text, src), dst, 10)


def test_whole_numbers_against_python_integers():
    rng = random.Random(8)
    for _ in range(300):
        n = rng.randint(0, 10**30)
        for base, spec in ((2, "b"), (8, "o"), (16, "x")):
            assert convert(str(n), 10, base) == format(n, spec)
            assert convert(format(n, spec), base, 10) == str(n)
        src, dst = rng.randint(2, 36), rng.randint(2, 36)
        assert int(convert(str(n), 10, src), src) == n
        assert convert(digits_of(n, src), src, dst) == digits_of(n, dst)


def test_a_dyadic_fraction_round_trips_exactly():
    rng = random.Random(3)
    for _ in range(200):
        text = "1." + "".join(rng.choice("01") for _ in range(rng.randint(1, 20)))
        decimal = convert(text, 2, 10, 30)
        assert parse_number(decimal, 10) == parse_number(text, 2)
        assert parse_number(convert(decimal, 10, 2, 30), 2) == parse_number(text, 2)


def test_the_cut_off_value_is_at_most_the_input_and_less_than_one_unit_below_it():
    rng = random.Random(21)
    for _ in range(200):
        src, dst = rng.randint(2, 36), rng.randint(2, 36)
        text = random_text(rng, src).lstrip("-")
        k = rng.randint(0, 12)
        value = parse_number(text, src)
        cut = parse_number(convert(text, src, dst, k), dst)
        assert cut <= value < cut + Fraction(1, dst**k)
