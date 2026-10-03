Create three Python modules (standard library only) that build a table of contents for a Markdown document: `headings.py` finds the headings, `toc.py` renders a list of headings as a nested list of links, and `inject.py` rewrites the table of contents inside a document. Documents are `str`; lines are separated by `"\n"` (a document is `text.split("\n")`, so a final newline gives a last empty line).

`headings.py` provides:

    Heading(level: int, text: str, line: int, anchor: str)        # frozen dataclass
    slugify(text: str) -> str
    fenced_lines(markdown: str) -> set[int]
    extract_headings(markdown: str) -> list[Heading]

`toc.py` provides:

    render_toc(headings: list[Heading], min_level: int = 1, max_level: int = 6) -> str

`inject.py` provides:

    find_markers(markdown: str) -> tuple[int, int]
    update_toc(markdown: str, min_level: int = 1, max_level: int = 6) -> str

`extract_headings`, `fenced_lines`, `find_markers` and `update_toc` raise `ValueError` when `markdown` is not a `str`.

Headings:

1. `slugify(text)` makes an anchor name: lower-case the text, keep only characters that are alphanumeric (`str.isalnum()`), `_`, `-` or the space character and drop all others (tabs and punctuation are dropped), then turn every space into one `-` (spaces are not merged). If nothing is left the result is `section`. Examples: `Hello, World!` gives `hello-world`; `a  b` gives `a--b`; `C++ & Rust` gives `c--rust`; `Snake_case-Name` gives `snake_case-name`; `Café` gives `café`; `!!!` gives `section`.
2. `fenced_lines(markdown)` returns the 1-based numbers of the lines that belong to a fenced code block, the opening and closing fence lines included. A fence opens on a line that has at most 3 spaces of indentation and then 3 or more backticks, or 3 or more tildes; any text may follow. It closes on the next line with at most 3 spaces of indentation, then only the same character (backtick or tilde) at least as many times as the opening fence used, then only spaces or tabs. A fence that is never closed lasts to the end of the document. Lines inside a fence are not examined for fences of the other kind or for anything else.
3. `extract_headings(markdown)` returns the ATX headings that are not in a fenced block, in document order. A heading line has at most 3 spaces of indentation, then 1 to 6 `#` characters, then at least one space or tab followed by the text (or nothing). `#hashtag` (no space after the `#`s), seven or more `#`, and lines indented 4 spaces or more are not headings. Underlined (setext) headings are not recognised. The heading text is the rest of the line stripped of surrounding whitespace, then stripped of an optional closing sequence: a trailing run of `#` characters that is the whole text or is preceded by a space or tab (`## Title ##` has the text `Title`; `C#` keeps its `#`), then stripped again. A heading whose text is empty (`##`, `## ##`) is skipped. The text is otherwise kept as written, inline markup included.
4. `Heading.level` is the number of `#` characters, `line` the 1-based line number in the document, and `anchor` is derived from `slugify(text)`: an anchor that no earlier returned heading has is used as it is, otherwise `-1`, `-2`, ... is appended to the slug, using the first suffix that gives an anchor no earlier heading has. So the headings `A`, `A`, `A-1`, `A` get the anchors `a`, `a-1`, `a-1-1`, `a-2`.

Table of contents:

5. `render_toc(headings, min_level, max_level)` raises `ValueError` unless `min_level` and `max_level` are `int`s from 1 to 6 (a `bool` is rejected) with `min_level <= max_level`. It keeps only the headings whose level is between them, inclusive, in their given order. Each kept heading becomes the line `<indent>- [<text>](#<anchor>)` where every `[` and `]` in the text is written `\[` and `\]`. The indent is 2 spaces for each open ancestor: keep a stack of the levels of the headings so far; for a new heading remove from the top of the stack every level that is greater than or equal to its level, its indent is 2 spaces times the size of the stack that remains, and then its level is pushed. So levels 1, 3, 2 are indented 0, 1 and 1 steps, and a document that starts at level 2 is not indented at all. The result is the lines joined with `"\n"` plus a final `"\n"`, or the empty string `""` when no heading is kept.

Updating a document:

6. The table of contents lives between a start marker line `<!-- toc -->` and an end marker line `<!-- /toc -->`. A marker is a line that equals the marker once surrounding whitespace is stripped, and that is not in a fenced block (see rule 2).
7. `find_markers(markdown)` returns `(start, end)`, the 0-based indexes of the marker lines in `markdown.split("\n")`. It raises `ValueError` unless there is exactly one start marker and exactly one end marker and the start comes before the end.
8. `update_toc(markdown, min_level, max_level)` finds the markers and replaces everything between them. The headings used are those of the document with the old content between the markers removed (so stale lines there never count as headings). Between the two marker lines the new content is: one empty line, then the lines of `render_toc` of those headings, then one empty line; when `render_toc` is empty, just the one empty line. Everything outside the marker region, including the marker lines themselves and whether the text ends with a newline, is kept exactly. The result of `update_toc` on its own output is the same text.

Example: the document

    # Title

    <!-- toc -->

    <!-- /toc -->

    ## Intro
    ### Details
    ## Usage

becomes

    # Title

    <!-- toc -->

    - [Title](#title)
      - [Intro](#intro)
        - [Details](#details)
      - [Usage](#usage)

    <!-- /toc -->

    ## Intro
    ### Details
    ## Usage
