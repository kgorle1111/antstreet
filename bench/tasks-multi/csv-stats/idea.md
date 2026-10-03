Create three Python modules (standard library only) that read CSV text, compute statistics on its columns and print text tables: `reader.py` parses the text into a `Table`, `stats.py` computes summaries and group totals over it, and `table.py` formats numbers and tables and prints a summary of a whole `Table`. `stats.py` knows `Table` only through the methods named below; `table.py` uses both other modules.

`reader.py` provides:

    Table(columns: tuple[str, ...], rows: tuple[tuple[str, ...], ...])      # frozen dataclass
    Table.column(name: str) -> list[str]
    Table.numbers(name: str) -> list[float | None]
    len(table) -> int
    read_table(text: str) -> Table

`stats.py` provides:

    Summary(count, missing, mean, minimum, maximum, median, stdev)           # frozen dataclass
    describe(values: Iterable[float | int | None]) -> Summary
    group_by(table: Table, key: str, value: str, func: str = "sum") -> dict

`table.py` provides:

    format_value(value) -> str
    render_table(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> str
    render_summary(table: Table) -> str

Reading:

1. `read_table(text)` raises `ValueError` if `text` is not a `str`. A leading byte order mark (`"﻿"`) is removed first. The text is CSV: fields are separated by commas; a field may be wrapped in double quotes, and inside quotes commas and line breaks are part of the field and a doubled quote `""` is one quote character. Line breaks outside quotes may be `\n`, `\r\n` or `\r`. A quoted field that is never closed raises `ValueError`. Field values are kept exactly as written (no stripping), as `str`.
2. A line with no characters at all is skipped (a line holding only `""` is a row with one empty field, not a skipped line). The first remaining record is the header: its names are stripped of surrounding whitespace and each must be non-empty, and they must all differ (case-sensitive), otherwise `ValueError`. Text with no remaining record at all raises `ValueError`. Every later record is a data row and must have exactly as many fields as the header, otherwise `ValueError`. A header with no data rows is a valid `Table` with no rows. `len(table)` is the number of data rows.
3. `Table.column(name)` returns a new list with that column's values (as `str`) in row order. `KeyError` for a name that is not a column.
4. `Table.numbers(name)` converts the column: a value that is empty or only whitespace becomes `None` (missing); any other value is stripped and must be a decimal number, meaning an optional sign, digits with an optional fraction (`.5`, `5.`, `5.25`) and an optional exponent (`1e3`, `2E-2`), and becomes a `float`. Anything else (`abc`, `1,000`, `1_000`, `nan`, `inf`, `0x10`, `1.2.3`, `--1`) raises `ValueError`, and so does a number too large to be finite. `KeyError` for an unknown column. Both are checked for the whole column before anything is returned.

Statistics:

5. `describe(values)` takes numbers (`int` or `float`) and `None`s, in any iterable. `count` is the number of numbers, `missing` the number of `None`s. For `count >= 1`, `mean`, `minimum`, `maximum` and `median` are floats; the median of an even count is the mean of the two middle values. `stdev` is the sample standard deviation (divide by `count - 1`) as a float, and `None` when `count < 2`. When `count == 0` all five of `mean`, `minimum`, `maximum`, `median` and `stdev` are `None`.
6. `group_by(table, key, value, func="sum")` groups the rows by their text in column `key` (the empty string is a group like any other) and aggregates the numbers of column `value` (from `Table.numbers`, so `None`s are skipped) with `func`, one of `"sum"`, `"mean"`, `"count"`, `"min"`, `"max"`; any other `func` raises `ValueError`, checked first. The result is a dict from group to result in order of the first appearance of each group. `"sum"` gives a float, `0.0` for a group with no numbers; `"count"` gives the int number of numbers in the group, so it is `0` for a group with none; `"mean"`, `"min"` and `"max"` give floats, and `None` for a group with no numbers. `KeyError` for an unknown column, `ValueError` if `value` has a non-numeric entry.

Formatting:

7. `format_value(value)` returns: `-` for `None`; for a `float`, 2 decimals exactly as `f"{value:.2f}"` writes them (`1234.5` is `1234.50`), except that a result of `-0.00` is written `0.00`; for any other value, `str(value)` (so an `int` is written as is).
8. `render_table(columns, rows)` returns a text table with one header line, one separator line and one line per row, each line ended by `"\n"`. Cells are `format_value` of each value (the header names are used as they are). Every column is as wide as its longest cell, header included. Cells of a line are joined with `" | "`, and the separator line is made of one run of `-` per column, as wide as the column, joined with `"-+-"`. A column is right-aligned (header too) when it has at least one value that is an `int` or a `float` (not a `bool`) and every value that is not `None` is such a number; otherwise it is left-aligned. After joining, trailing spaces are removed from every line. Every row must have as many cells as there are columns, otherwise `ValueError`, and at least one column is needed.
9. `render_summary(table)` describes every numeric column of the table: a column is numeric when `table.numbers(name)` succeeds and returns at least one number (a column that is not numeric, or has only missing values, is left out). It returns `render_table` of the columns `column`, `count`, `missing`, `mean`, `min`, `median`, `max`, `stdev` with one row per numeric column in table order, holding the name and the `describe` values (`count` and `missing` as ints, the rest as the floats or `None` from `describe`). When there is no numeric column it returns `No numeric columns.\n`.

Example: the text

    name,dept,salary,age
    Ann,eng,100,30
    Bob,eng,120,
    Cid,ops,80,41
    Dee,ops,,28

gives `render_summary`:

    column | count | missing |   mean |   min | median |    max | stdev
    -------+-------+---------+--------+-------+--------+--------+------
    salary |     3 |       1 | 100.00 | 80.00 | 100.00 | 120.00 | 20.00
    age    |     3 |       1 |  33.00 | 28.00 |  30.00 |  41.00 |  7.00
