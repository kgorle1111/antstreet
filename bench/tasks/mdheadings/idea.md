Create a Python module `mdheadings.py` (standard library only) with two functions that read the headings of a Markdown document:

    extract_headings(markdown: str) -> list[tuple[int, str, str]]
    heading_tree(markdown: str) -> list[dict]

`extract_headings` returns one `(level, title, anchor)` tuple for every heading, in document order. In this text, examples of input are written as Python string literals.

1. The text is split into lines at `\n`, and a `\r` at the end of a line is ignored. Only `#` headings count (no underlined headings). A heading line starts with one to six `#` in its first column, with no indentation, and then either ends or continues with a space or a tab. `level` is the number of `#`. So `'## A'` is a heading of level 2, while `'#A'` (no space after the `#`), `'####### A'` (seven `#`) and `' # A'` (indented) are not headings.
2. The title is the rest of the line without surrounding whitespace. A closing sequence is removed from it: if the title ends with one or more `#` that are preceded by a space or tab (or the whole title is `#` characters), those `#` and the whitespace before them are dropped. So `'## A ##'` has the title `"A"`, `'# A # B'` has the title `"A # B"` and `'## C#'` has the title `"C#"`, because the `#` is not preceded by whitespace. A heading whose title is empty (`'#'`, `'## '`, `'# #'`) is ignored. The rest of the title, including inline Markdown such as backticks or `*`, stays exactly as written.
3. Lines inside a fenced code block are not headings. A fence opens on a line that starts, in its first column, with three or more backticks or three or more tildes, followed by anything. It closes at the next line that starts with the same character repeated at least as many times as the opening line did (a line of tildes never closes a backtick fence, nor the reverse). A fence that is never closed runs to the end of the text. The fence lines themselves are not headings.
4. The `anchor` is made from the title: it is lowercased; every character that is not a letter or digit (as `str.isalnum` defines them), not a space, not `-` and not `_` is removed; and then every space is replaced by `-` (spaces are not merged: `'A  B'` gives `a--b`). `'Hello, World!'` gives `hello-world`, `'The `code` part'` gives `the-code-part`, and `'Café au lait'` gives `café-au-lait`. If nothing is left, the anchor is `section`.
5. Anchors are made unique in document order: the first heading with a given anchor keeps it, the second one gets `-1` added at the end, the third `-2`, and so on, counted separately for every base anchor. Two headings with the title `Setup` give `setup` and `setup-1`.

`heading_tree` returns the headings as a nested outline: a list of root nodes, each a dict with exactly the keys `"level"` (int), `"title"`, `"anchor"` (the same values `extract_headings` gives) and `"children"` (a list of nodes of the same shape, empty when there are none).

6. A heading is a child of the nearest heading before it that has a smaller level; a heading with no earlier heading of a smaller level is a root. Levels may be skipped: an `###` right after a `#` is a child of that `#`. Siblings keep document order.
7. Both functions raise `ValueError` when the argument is not a `str`. A text with no headings gives `[]`.
