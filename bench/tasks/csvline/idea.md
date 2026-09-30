Create a Python module `csvline.py` (standard library only) with two functions. Do not import the `csv` module; the module is judged on behaviour only, but the point is to write the parser yourself.

    parse_line(line: str) -> list[str]
    format_line(fields: list[str]) -> str

`parse_line` reads one CSV record (RFC 4180 rules) and returns its fields:

1. Fields are separated by commas. The empty string parses to `[""]`; `'a,,b'` parses to `["a", "", "b"]`; a trailing comma gives a trailing empty field (`'a,'` parses to `["a", ""]`, `','` to `["", ""]`). In this text, examples of input are written as Python string literals in single quotes.
2. A field that starts with a double quote is a quoted field and ends at its closing quote. Inside it, commas and line breaks (`\n` and `\r`, in any combination) are ordinary characters kept exactly as they are, and two double quotes in a row (`""`) stand for one double quote. The surrounding quotes are not part of the value: `'"a,b"'` parses to `["a,b"]`, `'""'` to `[""]`, `'"say ""hi"""'` to `['say "hi"']`.
3. Any other field is unquoted. Its text is everything up to the next comma or the end of the input, unchanged. An unquoted field must not contain a double quote. A double quote that does not open a field is an error, so `'a"b'` and `' "a"'` (a space before the quote makes the field unquoted) are errors.
4. After a closing quote the next character must be a comma or the input must end. Anything else is an error, including whitespace: `'"a" ,b'` and `'"a"b'` are errors.
5. A quoted field that is never closed is an error. `'"abc'` and `'"abc""'` are errors.
6. The input is one record. A line break (`\n` or `\r`) outside a quoted field is an error, including one at the very end of the input.
7. Whitespace is preserved exactly: `' a , b '` parses to `[" a ", " b "]`, and `'" a "'` to `[" a "]`. Nothing is ever stripped.
8. Every error raises `ValueError`.

`format_line` is the inverse: it joins the fields with commas into one record.

9. A field is wrapped in double quotes only when it contains a comma, a double quote, `\n` or `\r`, or when its first or last character is whitespace (as `str.isspace` defines it). Every other field is written as it is, so `'a b'` and the empty string stay unquoted.
10. Inside a quoted field every double quote is doubled. `'say "hi"'` is written `'"say ""hi"""'`, and a field that is a single double quote is written `'""""'`.
11. A field that is not a `str` (for example `None`, an `int` or `bytes`) raises `ValueError`, as does an empty list.
12. For every list of strings with at least one element, `parse_line(format_line(fields)) == fields`.
