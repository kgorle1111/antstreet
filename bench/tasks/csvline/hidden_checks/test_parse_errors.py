import pytest
from csvline import parse_line


@pytest.mark.parametrize("line", ['a"b', 'ab"', '"', 'a,b"c', 'a,b"', 'a,"'])
def test_quote_inside_unquoted_field_is_an_error(line):
    with pytest.raises(ValueError):
        parse_line(line)


@pytest.mark.parametrize("line", [' "a"', '"a" ,b', '"a"b', '"a" ', 'a,"b"c,d', '"a""b"c', '"a"\t'])
def test_text_after_closing_quote_is_an_error(line):
    with pytest.raises(ValueError):
        parse_line(line)


@pytest.mark.parametrize("line", ['"abc', '"abc""', '"a,b', 'x,"y', '"abc,def\nghi', '"""'])
def test_unterminated_quoted_field_is_an_error(line):
    with pytest.raises(ValueError):
        parse_line(line)


@pytest.mark.parametrize("line", ["a\nb", "a,b\n", "a\r\nb", "a,b\r", "\n", 'a,"b"\n', '"a"\r\n'])
def test_line_break_outside_quotes_is_an_error(line):
    with pytest.raises(ValueError):
        parse_line(line)
