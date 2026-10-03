Create a Python module `iniparse.py` (standard library only) with one function. Do not import `configparser`; the module is judged on behaviour only.

    parse_ini(text: str) -> dict[str, dict[str, str]]

`parse_ini` reads the text of an INI file and returns a dict that maps each section name to a dict of that section's keys and values, all strings. In this text, examples of input are written as Python string literals.

1. The text is split into lines at `\n`. Leading and trailing whitespace of every line is ignored (a `\r` before the `\n` counts as such whitespace, so `\r\n` line endings work). A line that is empty after that is skipped.
2. A comment line is one whose first character, after that stripping, is `;` or `#`. It is skipped. Comments exist only as whole lines: there are no inline comments, so `a = b ; c` has the value `b ; c`.
3. A section header is a line that starts with `[`. It must end with `]`, and the name is the text between the brackets with surrounding whitespace removed: `[ db ]` opens the section `db`, and `[a b]` opens the section `a b`. Names are case-sensitive. A header that does not end with `]`, or whose name is empty (`[]`, `[ ]`), is an error.
4. A section appears in the result as soon as its header is read, even when it has no keys (`[empty]` gives `{"empty": {}}`). A header for a section that was already opened continues that section: its earlier keys are kept and new keys are added to it.
5. Any other line is a key/value line. It is split at its first `=`: the key is the text before it and the value is the text after it, each with surrounding whitespace removed. The value may be empty (`k =` gives `""`) and may itself contain `=` (`url = a=b` gives the value `a=b`). A line without `=`, or with an empty key (`= v`), is an error. Keys are case-sensitive.
6. If a key appears again in the same section, the later value replaces the earlier one.
7. Key/value lines that come before any section header belong to the section named `""` (the empty string). That section is in the result only if at least one such line exists.
8. If a value (after the whitespace removal of rule 5) is at least two characters long and both starts and ends with a double quote, the first and last character are removed, and what is left is the value exactly as written, whitespace inside the quotes included: `k = "  x "` gives the value `  x ` (two spaces, `x`, one space), and `k = ""` gives `""`. There are no escape sequences, and single quotes are not special. Any other value, including a lone `"`, is left as it is.
9. Every error raises `ValueError`, and so does an argument that is not a `str`.
