import decimal
import math
import random

from bigdecimal import add, compare, multiply, subtract

CTX = decimal.Context(prec=5000, traps=[decimal.Inexact])


def canonical(value):
    return "0" if value == 0 else format(value.normalize(CTX), "f")


def random_number(rng, max_whole, max_frac):
    whole = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, max_whole)))
    text = "0" * rng.randint(0, 4) + whole
    if rng.random() < 0.75:
        frac = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, max_frac)))
        text += "." + frac + "0" * rng.randint(0, 3)
    return ("-" if rng.random() < 0.5 else "") + text


def test_random_large_operands_match_exact_decimal_arithmetic():
    rng = random.Random(7)
    for _ in range(40):
        a = random_number(rng, 150, 100)
        b = random_number(rng, 150, 100)
        x, y = decimal.Decimal(a), decimal.Decimal(b)
        assert add(a, b) == canonical(CTX.add(x, y)), (a, b)
        assert subtract(a, b) == canonical(CTX.subtract(x, y)), (a, b)
        assert multiply(a, b) == canonical(CTX.multiply(x, y)), (a, b)
        assert compare(a, b) == (x > y) - (x < y), (a, b)


def test_operands_of_very_different_sizes():
    rng = random.Random(11)
    for _ in range(20):
        a = random_number(rng, 200, 5)
        b = random_number(rng, 3, 150)
        x, y = decimal.Decimal(a), decimal.Decimal(b)
        assert add(a, b) == canonical(CTX.add(x, y)), (a, b)
        assert subtract(b, a) == canonical(CTX.subtract(y, x)), (b, a)
        assert multiply(a, b) == canonical(CTX.multiply(x, y)), (a, b)


def test_close_neighbours_that_only_differ_far_beyond_float_precision():
    base = "3." + "1415926535" * 20
    nudged = base + "1"
    assert subtract(nudged, base) == "0." + "0" * 200 + "1"
    assert compare(base, nudged) == -1
    assert add(base, "0." + "0" * 199 + "1") == "3." + "1415926535" * 19 + "141592653" + "6"


def test_fibonacci_by_repeated_addition_stays_exact():
    a, b = "0", "1"
    for _ in range(500):
        a, b = b, add(a, b)
    x, y = 0, 1
    for _ in range(500):
        x, y = y, x + y
    assert a == str(x)


def test_factorial_by_repeated_multiplication_stays_exact():
    product = "1"
    for n in range(2, 101):
        product = multiply(product, str(n))
    assert product == str(math.factorial(100))


def test_identities_on_huge_fractional_operands():
    a = "9" * 120 + "." + "9" * 120
    assert subtract(add(a, "1"), a) == "1"
    assert subtract(multiply(a, "10"), a) == multiply(a, "9")
