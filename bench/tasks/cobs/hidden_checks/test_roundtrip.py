import random

from cobs import decode, encode


def test_every_single_byte_and_every_pair_of_small_bytes_round_trip():
    for a in range(256):
        assert decode(encode(bytes([a]))) == bytes([a])
    for a in (0, 1, 2, 127, 128, 254, 255):
        for b in (0, 1, 2, 127, 128, 254, 255):
            data = bytes([a, b])
            assert decode(encode(data)) == data


def test_all_zero_inputs_of_many_lengths_round_trip():
    for n in range(0, 600, 7):
        data = bytes(n)
        assert decode(encode(data)) == data
        assert encode(data) == b"\x01" * (n + 1)


def test_runs_of_non_zero_bytes_of_every_length_near_the_block_size_round_trip():
    for n in list(range(0, 12)) + list(range(245, 265)) + list(range(500, 520)) + [762, 763, 1016]:
        for tail in (b"", b"\x00", b"\x00\x00", b"\x00\x07", b"\x07"):
            data = bytes((i % 255) + 1 for i in range(n)) + tail
            assert decode(encode(data)) == data, (n, tail)
            for lead in (b"\x00", b"\x00\x00"):
                assert decode(encode(lead + data)) == lead + data


def test_every_byte_value_in_order_round_trips():
    data = bytes(range(256)) * 3
    assert decode(encode(data)) == data


def test_random_data_with_few_zeros_round_trips():
    rng = random.Random(254)
    for _ in range(300):
        n = rng.randrange(0, 1200)
        data = bytes(0 if rng.random() < 0.004 else rng.randrange(1, 256) for _ in range(n))
        assert decode(encode(data)) == data


def test_random_data_with_many_zeros_round_trips():
    rng = random.Random(1)
    for _ in range(300):
        n = rng.randrange(0, 80)
        data = bytes(0 if rng.random() < 0.5 else rng.randrange(1, 256) for _ in range(n))
        assert decode(encode(data)) == data


def test_random_bytes_round_trip():
    rng = random.Random(7)
    for _ in range(300):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 700)))
        assert decode(encode(data)) == data


def test_the_encoding_never_contains_a_zero_byte():
    rng = random.Random(3)
    for _ in range(300):
        data = bytes(
            rng.choice([0, 0, 1, 255, rng.randrange(256)]) for _ in range(rng.randrange(0, 700))
        )
        assert 0 not in encode(data)
    assert 0 not in encode(bytes(1000))
    assert 0 not in encode(bytes(range(256)) * 5)


def test_the_encoding_is_never_longer_than_the_bound():
    rng = random.Random(11)
    for _ in range(300):
        data = bytes(
            rng.choice([0, 1, 2, 3]) if rng.random() < 0.05 else rng.randrange(1, 256)
            for _ in range(rng.randrange(0, 1500))
        )
        assert len(encode(data)) <= len(data) + len(data) // 254 + 1


def test_packets_joined_by_a_zero_delimiter_can_be_split_and_decoded():
    packets = [b"", b"\x00", b"hello", b"a\x00b", bytes(300), bytes(range(256)), b"\x00\x00"]
    stream = b"".join(encode(p) + b"\x00" for p in packets)
    pieces = stream.split(b"\x00")
    assert pieces[-1] == b""
    assert [decode(piece) for piece in pieces[:-1]] == packets


def test_an_encoding_can_be_decoded_after_being_copied_to_a_bytearray():
    for data in (b"", b"\x00", b"abc\x00def", bytes(range(1, 256)) * 2):
        assert decode(bytearray(encode(data))) == data
