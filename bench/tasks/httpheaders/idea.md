Create a Python module `httpheaders.py` (standard library only) that parses a block of HTTP header lines into an object with case-insensitive lookup. It provides one function and one class:

    parse_headers(text: str) -> Headers
    class Headers:
        def get(self, name: str, default: str | None = None) -> str | None
        def get_all(self, name: str) -> list[str]
        def items(self) -> list[tuple[str, str]]
        def __contains__(self, name: object) -> bool
        def __len__(self) -> int

`text` holds header lines only (no request line or status line). In this text, examples of input are written as Python string literals.

Parsing:

1. Lines end with `\n` or `\r\n`, in any mix. A line that is empty (no characters at all) ends the block: it and everything after it are ignored, even text that would be invalid as headers (`'A: 1\r\n\r\nthis is a body'` has one header). A block that is empty or starts with an empty line has no headers. A missing final line ending is fine.
2. A header line is a name, a `:`, and a value, split at the first `:` (the value may hold more colons: `'Host: example.com:8080'` has the value `example.com:8080`). The name is one or more of the letters `A-Z` and `a-z`, the digits, and the characters `` !#$%&'*+-.^_`|~ ``; so a name with a space, including a space before the colon (`'Name : x'`), is an error. The value is the text after the colon with leading and trailing spaces and tabs removed; it may be empty (`'X:'` has the value `""`). The name keeps the spelling it had in the text.
3. A line that starts with a space or a tab continues the header above it (a folded line). The value of the header is its own stripped value and the stripped text of each continuation line, with the parts that are not empty joined by a single space: `'A: one\r\n  two\r\n\tthree'` gives `A` the value `one two three`, and `'A:\r\n  two'` gives `two`. A continuation line that is blank after stripping adds nothing. A continuation line with no header above it (it is the first line) is an error.
4. A line with no `:`, or an empty name (`':x'`), is an error, as is a name with a character that is not allowed.
5. All errors are `ValueError`. A `text` that is not a `str` raises `TypeError`.

The `Headers` object:

6. `items()` returns a new list of `(name, value)` pairs, one for every header in the order of the text, with the names as spelled there. Repeated headers are separate entries. `len(headers)` is the number of those entries (a folded header counts once).
7. Names are compared without regard to case, but only for the ASCII letters: `Content-Type`, `content-type` and `CONTENT-TYPE` are the same name; a name with a non-ASCII character is never equal to an ASCII one (the Kelvin sign `\u212a` is not `k`). This holds for `get`, `get_all` and `in`.
8. `get_all(name)` returns the values of every header with that name, in text order, as a list; it is empty when there is none. `get(name, default=None)` returns the values of all headers with that name joined with `', '` in text order (so a single header gives its value as it is), and `default` when there is none. `name in headers` is `True` when there is at least one header with that name, and `False` for any `name` that is not a `str`.
