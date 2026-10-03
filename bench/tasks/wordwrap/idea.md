Create a Python module `wordwrap.py` (standard library only) with one function. Do not import `textwrap`; the module is judged on behaviour only.

    wrap(text: str, width: int, first_indent: str = "", rest_indent: str = "") -> list[str]

`wrap` breaks text into lines of at most `width` characters and returns them as a list of strings, without line-end characters.

1. The words of `text` are what `str.split()` gives: runs of any whitespace, newlines included, separate words and are dropped. Text with no words gives the empty list `[]`.
2. Wrapping is greedy: words are placed in order, and a word goes on the current line, after a single space, whenever the line would then still be at most `width` characters long. Otherwise the line is finished and the word starts the next line. A line never starts or ends with a space (apart from its indent) and is never empty.
3. The first line starts with `first_indent` and every later line starts with `rest_indent`. Both are any strings (`"  "`, `"- "`, `"\t"`), and every character of an indent counts as one character of the line's length, so the indent uses up part of `width`.
4. A word that is longer than the room a line has after its indent (`width` minus the length of that line's indent) can never fit, so it is cut into pieces. The line that is open when such a word comes is finished first, and the word is not added to it. Each piece, taken from the front of the word, has exactly as many characters as fit after the indent of the line it goes on, and goes on a line of its own; what is left of the word, if it fits, starts a new line like any word and the next words may follow it on that line as in rule 2. A word that exactly fills a line is not cut. Example: with width 5, `"abcdefghijkl x"` gives `["abcde", "fghij", "kl x"]`.
5. `width` must be an `int` and each indent must leave room for at least one character (`width - len(first_indent) >= 1` and `width - len(rest_indent) >= 1`). Otherwise, and when `text` or either indent is not a `str`, `wrap` raises `ValueError`. This is checked before anything else, also for text without words.
