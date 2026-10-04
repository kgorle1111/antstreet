import pytest
from netstring import Decoder


@pytest.mark.parametrize(
    "data",
    [
        b"5:hello;",
        b"5:hello:",
        b"5:hello5",
        b"5:hello ",
        b"5:hello\n",
        b"3:abcd",
        b"0:x",
        b"1:ab,",
        b"0:0:,",
    ],
)
def test_a_byte_other_than_a_comma_after_the_payload_raises(data):
    with pytest.raises(ValueError):
        Decoder().feed(data)


def test_the_bad_terminator_is_caught_when_it_arrives_in_a_later_piece():
    d = Decoder()
    assert d.feed(b"3:abc") == []
    with pytest.raises(ValueError):
        d.feed(b";")


def test_a_payload_that_is_longer_than_its_length_raises():
    with pytest.raises(ValueError):
        Decoder().feed(b"2:abc,")


def test_a_payload_shorter_than_its_length_swallows_the_comma_and_waits():
    d = Decoder()
    assert d.feed(b"4:abc,") == []
    assert d.feed(b",") == [b"abc,"]


def test_the_default_limit_is_one_million():
    assert Decoder().feed(b"1000000:") == []
    with pytest.raises(ValueError):
        Decoder().feed(b"1000001:")
    with pytest.raises(ValueError):
        Decoder().feed(b"999999999:")


def test_a_length_equal_to_the_limit_is_accepted_and_one_above_raises():
    d = Decoder(max_length=10)
    assert d.feed(b"10:") == []
    assert d.feed(b"0123456789,") == [b"0123456789"]
    with pytest.raises(ValueError):
        Decoder(max_length=10).feed(b"11:")


def test_the_limit_is_checked_at_the_colon_before_any_payload_arrives():
    d = Decoder(max_length=5)
    assert d.feed(b"6") == []
    with pytest.raises(ValueError):
        d.feed(b":")


def test_a_limit_of_zero_accepts_only_empty_frames():
    d = Decoder(max_length=0)
    assert d.feed(b"0:,0:,") == [b"", b""]
    with pytest.raises(ValueError):
        Decoder(max_length=0).feed(b"1:")


def test_a_limit_applies_to_every_frame_in_the_stream():
    with pytest.raises(ValueError):
        Decoder(max_length=3).feed(b"3:abc,4:")


def test_a_larger_limit_allows_larger_frames():
    payload = b"z" * 2_000_000
    d = Decoder(max_length=2_000_000)
    assert d.feed(b"2000000:" + payload + b",") == [payload]
