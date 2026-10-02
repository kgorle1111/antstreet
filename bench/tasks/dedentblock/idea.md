Create a Python module `dedentblock.py` (standard library only) with two functions. Do not import `textwrap`; the module is judged on behaviour only.

    common_margin(text: str) -> str
    dedent(text: str) -> str

Both treat `text` as lines separated by `\n`. In this text, examples of input are written as Python string literals.

1. A line is blank when it is empty or consists only of spaces and tabs. Only the space and the tab count as indentation or blank-making characters; any other character (a non-breaking space ` `, a form feed, `\r`, ...) is ordinary content. In particular `\r` is not removed or treated as a line end: `'  a\r\n  b'` has the two lines `'  a\r'` and `'  b'`.
2. The indentation of a line is the run of spaces and tabs at its start.
3. `common_margin(text)` returns the longest string that is the start of the indentation of every non-blank line. The comparison is character by character, so a tab and a space are different characters: the margin of `'\tx\n    y'` is `""`, and the margin of `'\t  x\n\t\ty'` is `"\t"`. Blank lines are ignored, whatever they contain. If there is no non-blank line, the margin is `""`.
4. `dedent(text)` removes the margin from the start of every non-blank line and returns the lines joined with `\n` again. Every blank line, whatever spaces or tabs it held, becomes the empty string. The number of lines never changes: a trailing `\n` in the input is still there in the output, and so are empty lines. Nothing else is changed: text after the margin, including its own indentation and trailing whitespace, is kept exactly. If there is no non-blank line, every line becomes empty, so `'  \n\t'` becomes `'\n'`.
5. A line whose indentation is longer than the margin keeps the extra part: `dedent('  a\n      b')` is `'a\n    b'`.
6. Both functions raise `ValueError` when `text` is not a `str`.
