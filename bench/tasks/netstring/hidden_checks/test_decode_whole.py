from netstring import Decoder


def test_one_frame_in_one_piece():
    assert Decoder().feed(b"5:hello,") == [b"hello"]


def test_several_frames_in_one_piece_come_back_in_order():
    assert Decoder().feed(b"5:hello,3:abc,0:,1:z,") == [b"hello", b"abc", b"", b"z"]


def test_an_empty_payload():
    assert Decoder().feed(b"0:,") == [b""]
    assert Decoder().feed(b"0:,0:,0:,") == [b"", b"", b""]


def test_a_payload_may_contain_delimiters_digits_and_binary():
    d = Decoder()
    assert d.feed(b"6:3:abc,,") == [b"3:abc,"]
    assert d.feed(b"3:\n\x00\xff,") == [b"\n\x00\xff"]
    assert d.feed(b"4:,,,,,") == [b",,,,"]
    assert d.feed(b"3::::,") == [b":::"]


def test_the_payload_is_bytes_even_when_a_bytearray_was_fed():
    out = Decoder().feed(bytearray(b"2:hi,1:x,"))
    assert out == [b"hi", b"x"]
    assert all(type(p) is bytes for p in out)
    assert type(Decoder().feed(b"")) is list


def test_the_length_counts_bytes_not_characters():
    assert Decoder().feed(b"2:\xc3\xa9,") == ["\u00e9".encode()]


def test_multi_digit_lengths():
    assert Decoder().feed(b"10:0123456789,") == [b"0123456789"]
    payload = b"q" * 4321
    assert Decoder().feed(b"4321:" + payload + b",") == [payload]


def test_a_zero_length_digit_after_the_first_position_is_not_a_leading_zero():
    assert Decoder().feed(b"10:" + b"a" * 10 + b",") == [b"a" * 10]
    assert Decoder().feed(b"100:" + b"a" * 100 + b",") == [b"a" * 100]


def test_a_decoder_keeps_working_across_many_frames():
    d = Decoder()
    for n in range(0, 50):
        payload = bytes((i * 7 + n) % 256 for i in range(n))
        assert d.feed(str(n).encode() + b":" + payload + b",") == [payload]
