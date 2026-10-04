import random

from netstring import Decoder, encode


def feed_all(pieces):
    d = Decoder()
    out = []
    for piece in pieces:
        out += d.feed(piece)
    d.close()
    return out


def test_the_example_from_the_idea():
    d = Decoder()
    assert d.feed(b"5:he") == []
    assert d.feed(b"llo,3:abc,") == [b"hello", b"abc"]


def test_a_frame_is_complete_only_when_its_comma_arrives():
    d = Decoder()
    assert d.feed(b"5:hello") == []
    assert d.feed(b",") == [b"hello"]


def test_one_byte_at_a_time():
    stream = b"5:hello,0:,3:a,b,12:hello world!,"
    assert feed_all([stream[i : i + 1] for i in range(len(stream))]) == [
        b"hello",
        b"",
        b"a,b",
        b"hello world!",
    ]


def test_a_split_inside_the_length_digits():
    d = Decoder()
    assert d.feed(b"1") == []
    assert d.feed(b"2") == []
    assert d.feed(b":hello ") == []
    assert d.feed(b"world!,") == [b"hello world!"]


def test_a_split_right_after_the_colon_and_right_before_it():
    d = Decoder()
    assert d.feed(b"3") == []
    assert d.feed(b":") == []
    assert d.feed(b"abc") == []
    assert d.feed(b",") == [b"abc"]


def test_an_empty_piece_changes_nothing():
    d = Decoder()
    assert d.feed(b"") == []
    assert d.feed(b"3:ab") == []
    assert d.feed(b"") == []
    assert d.feed(bytearray()) == []
    assert d.feed(b"c,") == [b"abc"]
    assert d.feed(b"") == []


def test_a_payload_is_returned_only_once():
    d = Decoder()
    assert d.feed(b"3:abc,") == [b"abc"]
    assert d.feed(b"1:x,") == [b"x"]
    assert d.feed(b"") == []


def test_a_piece_may_end_one_frame_and_start_the_next():
    d = Decoder()
    assert d.feed(b"3:abc,2:d") == [b"abc"]
    assert d.feed(b"e,4:") == [b"de"]
    assert d.feed(b"wxyz,") == [b"wxyz"]


def test_a_large_payload_in_small_pieces():
    payload = bytes(range(256)) * 40
    stream = encode(payload)
    pieces = [stream[i : i + 97] for i in range(0, len(stream), 97)]
    assert feed_all(pieces) == [payload]


def test_every_split_of_a_stream_into_two_pieces():
    payloads = [b"hello", b"", b"a:b,c", b"\x00\x01\x02", b"x" * 11]
    stream = b"".join(map(encode, payloads))
    for cut in range(len(stream) + 1):
        assert feed_all([stream[:cut], stream[cut:]]) == payloads, cut


def test_random_partitions_of_random_streams():
    rng = random.Random(20261002)
    for _ in range(200):
        payloads = [
            bytes(rng.randrange(256) for _ in range(rng.choice([0, 1, 2, 5, 11, 30])))
            for _ in range(rng.randrange(0, 6))
        ]
        stream = b"".join(map(encode, payloads))
        cuts = sorted(rng.randrange(len(stream) + 1) for _ in range(rng.randrange(0, 6)))
        edges = [0, *cuts, len(stream)]
        pieces = [stream[a:b] for a, b in zip(edges, edges[1:], strict=False)]
        assert feed_all(pieces) == payloads
