import random

from leb128 import decode_signed, decode_unsigned, encode_signed, encode_unsigned


def test_every_small_value_round_trips():
    for value in range(0, 70000, 3):
        encoded = encode_unsigned(value)
        assert decode_unsigned(encoded) == (value, len(encoded))
    for value in range(-40000, 40000, 3):
        encoded = encode_signed(value)
        assert decode_signed(encoded) == (value, len(encoded))


def test_the_edges_of_every_group_boundary_round_trip():
    for bits in range(0, 64):
        for delta in (-2, -1, 0, 1, 2):
            value = 2**bits + delta
            if 0 <= value < 2**64:
                encoded = encode_unsigned(value)
                assert decode_unsigned(encoded) == (value, len(encoded)), value
            for signed in (value, -value):
                if -(2**63) <= signed < 2**63:
                    encoded = encode_signed(signed)
                    assert decode_signed(encoded) == (signed, len(encoded)), signed


def test_the_extremes_of_every_width_round_trip():
    for bits in (1, 2, 7, 8, 9, 14, 15, 16, 21, 32, 33, 63, 64, 65, 100, 128):
        for value in (0, 1, 2**bits - 1, 2**bits - 2):
            if 0 <= value < 2**bits:
                encoded = encode_unsigned(value, bits)
                assert decode_unsigned(encoded, 0, bits) == (value, len(encoded))
        low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
        for value in (low, low + 1, -1, 0, high - 1, high):
            if low <= value <= high:
                encoded = encode_signed(value, bits)
                assert decode_signed(encoded, 0, bits) == (value, len(encoded)), (value, bits)


def test_random_values_round_trip_at_random_widths():
    rng = random.Random(128)
    for _ in range(2000):
        bits = rng.choice([8, 16, 21, 32, 64, 70])
        u = rng.randrange(0, 2**bits)
        s = rng.randrange(-(2 ** (bits - 1)), 2 ** (bits - 1))
        eu, es = encode_unsigned(u, bits), encode_signed(s, bits)
        assert decode_unsigned(eu, 0, bits) == (u, len(eu))
        assert decode_signed(es, 0, bits) == (s, len(es))


def test_random_streams_decode_back_to_the_values_in_order():
    rng = random.Random(7)
    for _ in range(100):
        values = [rng.randrange(-(2**63), 2**63) for _ in range(rng.randrange(0, 12))]
        data = b"".join(encode_signed(v) for v in values)
        out, offset = [], 0
        while offset < len(data):
            v, offset = decode_signed(data, offset)
            out.append(v)
        assert out == values
