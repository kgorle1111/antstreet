import pytest
from netstring import Decoder


@pytest.mark.parametrize(
    "data",
    [
        b"x",
        b":",
        b"-",
        b" ",
        b"\n",
        b",",
        b"a1:b,",
        b"-1:a,",
        b" 5:hello,",
        b":,",
        b"+3:abc,",
        b"\xff",
    ],
)
def test_a_first_byte_that_is_not_a_digit_raises_at_once(data):
    with pytest.raises(ValueError):
        Decoder().feed(data)


@pytest.mark.parametrize("data", [b"00", b"00:,", b"01", b"01:a,", b"05:hello,", b"007:abcdefg,"])
def test_a_leading_zero_raises_at_the_second_digit(data):
    with pytest.raises(ValueError):
        Decoder().feed(data)


def test_zero_alone_is_a_good_length():
    d = Decoder()
    assert d.feed(b"0") == []
    assert d.feed(b":,") == [b""]


@pytest.mark.parametrize("data", [b"1234567890", b"1234567890:", b"0000000000", b"99999999999:"])
def test_a_tenth_digit_raises(data):
    with pytest.raises(ValueError):
        Decoder(max_length=10**12).feed(data)


def test_nine_digits_are_still_read():
    d = Decoder(max_length=10**9)
    assert d.feed(b"123456789") == []
    assert d.feed(b":") == []
    assert Decoder(max_length=10**9).feed(b"999999999:") == []


@pytest.mark.parametrize("data", [b"12x", b"12 ", b"12,", b"12-", b"3\n", b"3a:", b"12.5:"])
def test_a_byte_after_the_digits_that_is_not_a_digit_or_colon_raises(data):
    with pytest.raises(ValueError):
        Decoder().feed(data)


def test_the_error_is_raised_before_more_data_arrives():
    d = Decoder()
    d.feed(b"1")
    with pytest.raises(ValueError):
        d.feed(b"x")
    d2 = Decoder()
    with pytest.raises(ValueError):
        d2.feed(b"5:hello,x")


def test_a_bad_byte_in_a_later_frame_raises():
    with pytest.raises(ValueError):
        Decoder().feed(b"3:abc,x5:hello,")
    with pytest.raises(ValueError):
        Decoder().feed(b"3:abc,05:hello,")
