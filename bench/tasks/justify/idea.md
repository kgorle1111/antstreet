Create a Python module `justify.py` (standard library only) with one function:

    justify(text: str, width: int) -> list[str]

It lays text out as lines of exactly `width` characters, fully justified:

1. `width` below 1 raises `ValueError`, whatever the text is (even empty text).
2. The text is split into words on whitespace (spaces, tabs and newlines, any amount of them);
   leading, trailing and repeated whitespace does not matter. The words keep their order and are
   never split or altered.
3. A word longer than `width` raises `ValueError`. A word exactly `width` long is fine.
4. Empty or whitespace-only text gives an empty list.
5. Lines are packed greedily: each line takes as many of the next words as fit when they are
   separated by single spaces (the line's length with single spaces must be at most `width`); the
   next word starts the following line.
6. Every line except the last is then justified: the spaces between its words are widened so the
   line is exactly `width` characters, with every gap at least one space. The extra spaces are
   spread as evenly as possible, and when they do not divide evenly the leftmost gaps get one
   more space than the others.
7. A line holding a single word is left-aligned: the word followed by trailing spaces up to
   `width`, even when it is not the last line.
8. The last line is left-aligned: its words are separated by single spaces and it is padded with
   trailing spaces up to `width`. If the whole text fits on one line, that line is the last line.
9. Every returned line is exactly `width` characters long. Returned lines are not stripped.
