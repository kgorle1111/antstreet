from table import format_value


def test_none():
    assert format_value(None) == "-"


def test_floats_have_two_decimals():
    assert format_value(1234.5) == "1234.50"
    assert format_value(0.0) == "0.00"
    assert format_value(3.14159) == "3.14"
    assert format_value(100.0) == "100.00"
    assert format_value(-2.5) == "-2.50"
    assert format_value(1e6) == "1000000.00"


def test_negative_zero_is_written_without_a_sign():
    assert format_value(-0.0) == "0.00"
    assert format_value(-0.001) == "0.00"
    assert format_value(-0.004) == "0.00"
    assert format_value(-0.006) == "-0.01"


def test_rounding_of_a_representable_half():
    assert format_value(0.125) == "0.12"
    assert format_value(2.675) == "2.67"
    assert format_value(0.5) == "0.50"


def test_ints_and_text_are_written_as_is():
    assert format_value(7) == "7"
    assert format_value(0) == "0"
    assert format_value(-3) == "-3"
    assert format_value("abc") == "abc"
    assert format_value("") == ""
    assert format_value(True) == "True"
    assert format_value([1, 2]) == "[1, 2]"
