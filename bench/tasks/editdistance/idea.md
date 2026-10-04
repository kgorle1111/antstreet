Create a Python module `editdistance.py` (standard library only) with two functions:

    edit_distance(a: str, b: str) -> int
    edit_script(a: str, b: str) -> list[tuple[str, ...]]

1. The distance is the Levenshtein distance: the fewest single-character edits that turn `a` into
   `b`, where an edit is inserting one character, deleting one character, or replacing one
   character with a different one, and each costs 1. Characters are compared as they are (code
   point by code point, so `"A"` and `"a"` differ). `edit_distance("kitten", "sitting")` is 3,
   `edit_distance("", "abc")` is 3 and `edit_distance("abc", "abc")` is 0.
2. `edit_script(a, b)` returns the alignment as a list of operations, read left to right. Each
   operation is a tuple of one of four shapes:
   - `("keep", c)`: the next character of `a` and the next character of `b` are both `c`
   - `("sub", x, y)`: the next character of `a` is `x`, it is replaced by the next character of
     `b`, which is `y`, and `x != y`
   - `("delete", x)`: the next character of `a` is `x` and it is removed
   - `("insert", y)`: the next character of `b` is `y` and it is added

   Together the operations use every character of `a` once, in order, and every character of `b`
   once, in order. The number of operations that are not `keep` equals `edit_distance(a, b)`, so
   the script is a cheapest one. Two empty strings give `[]`.
3. Many cheapest scripts can exist. Return the one whose list of operation names (`"keep"`,
   `"sub"`, `"delete"`, `"insert"`) is smallest when compared position by position, with the order
   `keep` < `sub` < `delete` < `insert`: at the first position where two cheapest scripts use
   different operations, the one with the earlier operation in that order wins. The characters
   follow from the operations, so this picks exactly one script. For example:
   - `edit_script("kitten", "sitting")` is `[("sub", "k", "s"), ("keep", "i"), ("keep", "t"),
     ("keep", "t"), ("sub", "e", "i"), ("keep", "n"), ("insert", "g")]`
   - `edit_script("ab", "ba")` is `[("sub", "a", "b"), ("sub", "b", "a")]`
   - `edit_script("aab", "ab")` is `[("keep", "a"), ("delete", "a"), ("keep", "b")]`
   - `edit_script("flaw", "lawn")` is `[("delete", "f"), ("keep", "l"), ("keep", "a"),
     ("keep", "w"), ("insert", "n")]`
4. An argument that is not a `str` raises `TypeError`, from both functions.
5. Strings of a few hundred characters each must be handled in a few seconds.
