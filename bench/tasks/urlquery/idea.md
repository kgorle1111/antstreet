Create a Python module `urlquery.py` (standard library only) with two functions. Do not import `urllib`; the module is judged on behaviour only, but the point is to write the parser and encoder yourself.

    parse_query(qs: str) -> dict[str, list[str]]
    build_query(params: dict) -> str

`parse_query` reads a URL query string such as `a=1&b=2&a=3`. In this text, examples of input are written as Python string literals.

1. A single leading `?` is removed first (`'?a=1'` is read as `'a=1'`; `'??a=1'` is read as `'?a=1'`, so its key is `"?a"`).
2. The rest is split at `&` into segments. An empty segment is skipped (`'a=1&&b=2'`, `'a=1&'` and `''` have no empty entries; `''` gives `{}`).
3. A segment is split at its first `=` into a key and a value; the value may itself contain `=`. A segment with no `=` has the value `""` (`'flag'` gives `{"flag": [""]}`). A segment whose key is empty before decoding (`'=x'`, `'='`) is skipped.
4. The key and the value are each decoded in this way: `+` becomes a space, and `%XX` (two hexadecimal digits, upper or lower case) is one byte; the bytes are then read as UTF-8, so `'%C3%A9'` is `"é"`. `%2B` is a literal `+`, not a space. A `%` that is not followed by two hexadecimal digits (`'%'`, `'%4'`, `'%zz'`), or bytes that are not valid UTF-8, are errors.
5. The result maps each decoded key to the list of its decoded values in the order they appear, so repeated keys collect all their values (`'a=1&b=2&a=3'` gives `{"a": ["1", "3"], "b": ["2"]}`). Keys are in the order of their first appearance. Two different spellings that decode to the same key (`'a%20b=1&a+b=2'`) are the same key.

`build_query` is the reverse.

6. `params` is a dict. Each value is either a `str`, which counts as a list of that one string, or a `list` or `tuple` of `str`. The result has one `key=value` pair for every value, joined with `&`, with keys in the dict's order and each key's values in list order. A key with an empty list gives no pairs. An empty dict gives `""`. There is no leading `?`.
7. Keys and values are encoded as UTF-8 bytes. The characters `A-Z`, `a-z`, `0-9`, `-`, `.`, `_` and `~` are written as they are, a space is written as `+`, and every other byte is written as `%` and two uppercase hexadecimal digits (`'a b&c'` becomes `a+b%26c`, `'é'` becomes `%C3%A9`, `'+'` becomes `%2B`). An empty value is written as `key=`.
8. A key that is not a `str`, an empty key, a value that is not a `str`, `list` or `tuple`, a list item that is not a `str`, or an argument that is not a `dict` raises `ValueError`. `parse_query` raises `ValueError` too when its argument is not a `str`.
9. For every dict whose keys are non-empty strings and whose values are non-empty lists of strings, `parse_query(build_query(params))` equals `params`.
