Create a Python module `wildcard.py` (standard library only) that matches names against glob-style patterns. Do not import `fnmatch`, `glob` or `re`: implement the matching yourself. (The scoring only checks behaviour, not imports.) The module has two functions:

    match(pattern: str, text: str) -> bool
    filter_names(pattern: str, names: Iterable[str]) -> list[str]

`match` returns True when the whole `text` matches the whole `pattern`, and False otherwise. Matching is case-sensitive and works on characters (Unicode code points). No character of the text is special: `*` and `?` also match `/`, `.` and newlines.

Pattern syntax:

1. An ordinary character matches only itself. The empty pattern matches only the empty text. A `]` outside a set is an ordinary character.
2. `*` matches any run of characters, including none. `?` matches exactly one character.
3. `[...]` is a set. It matches exactly one character that is a member of the set. A member is either a single character or a range `x-y`, which contains every character from `x` to `y` inclusive, compared by code point. A range whose start is above its end contains nothing.
4. A `-` is a range operator only when it sits between two members. A `-` that is the first member of the set, or the last one just before the closing `]`, is an ordinary member: `[a-]` matches `a` and `-`, and `[-a]` does the same.
5. `[!...]` is a negated set: it matches exactly one character that is not a member. The `!` is only special directly after the `[`; anywhere else it is an ordinary member. `^` has no special meaning at all: `[^a]` matches `^` and `a`.
6. A `]` directly after `[` or directly after `[!` is an ordinary member, not the end of the set. So `[]]` matches `]`, `[]a]` matches `]` or `a`, and `[!]]` matches any one character except `]`. In every other position the first `]` ends the set, so `[a]]` is the set `[a]` followed by a literal `]`.
7. Inside a set, `*`, `?` and `[` are ordinary members.
8. A backslash escapes the next character, both outside and inside a set: that character is then matched literally, whatever it is. `\*`, `\?`, `\[` and `\\` match `*`, `?`, `[` and a backslash. An escaped `]` inside a set is a member and does not close it. An escaped `-` inside a set is a member and is never a range operator, so `[a\-z]` matches only `a`, `-` and `z`. An escaped `!` directly after `[` is a member, not a negation. A backslash before any other character just means that character. Either end of a range may be an escaped character.
9. A pattern that ends with a lone backslash raises `ValueError`. (`\\` at the end is an escaped backslash and is fine; three backslashes at the end are not.) A `[` whose set is never closed raises `ValueError`. So do `[`, `[]`, `[!]`, `[abc` and `[a\]`.
10. The pattern is always checked in full, whatever the text is. `match("abc[", "x")` and `match("[", "")` raise `ValueError` even though the text could never match. `filter_names` also raises `ValueError` for such a pattern when `names` is empty.

Running time:

11. Matching must take polynomial time in the lengths of the pattern and the text. Texts of up to 10,000 characters and patterns of up to 100 characters must be handled without error in about a second or less. For example `match("a*a*a*a*a*b", "a" * 10000)` must return False right away. Do not let repeated `*` cause exponential backtracking, and do not rely on deep recursion.

`filter_names(pattern, names)`:

12. `names` is any iterable of strings. Returns a new list holding the names that match `pattern`, in their original order, with duplicates kept. It returns `[]` when nothing matches.
