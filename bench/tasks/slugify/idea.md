Create a Python module `slugify.py` (standard library only) with one function:

    slugify(text: str, max_length: int | None = None) -> str

It turns a title into a URL slug:

1. Accented letters become their plain ASCII letter (é becomes e, ü becomes u). Characters with
   no ASCII form are dropped.
2. Everything is lowercased.
3. Every run of characters other than a-z and 0-9 becomes a single hyphen.
4. The slug has no leading or trailing hyphen. Text with no letters or digits gives "".
5. If `max_length` is given and the slug is longer than it, cut the slug at the last hyphen such
   that the result is at most `max_length` characters. If the first word alone is longer than
   `max_length`, cut that word to exactly `max_length` characters. The result never ends with a
   hyphen.
6. A `max_length` below 1 raises `ValueError`.
