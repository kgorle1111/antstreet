# Same as the reference; the bug is in reader.py: A row with fewer fields than the header is
# accepted instead of rejected.
from stats import describe

_SUMMARY_COLUMNS = ["column", "count", "missing", "mean", "min", "median", "max", "stdev"]


def format_value(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        text = f"{value:.2f}"
        return "0.00" if text == "-0.00" else text
    return str(value)


def _is_number(value):
    return isinstance(value, int | float) and not isinstance(value, bool)


def render_table(columns, rows):
    columns = list(columns)
    rows = [list(row) for row in rows]
    if not columns:
        raise ValueError("a table needs at least one column")
    for number, row in enumerate(rows, 1):
        if len(row) != len(columns):
            raise ValueError(f"row {number} has {len(row)} cells, expected {len(columns)}")
    cells = [[format_value(value) for value in row] for row in rows]
    widths = [max([len(name), *(len(row[i]) for row in cells)]) for i, name in enumerate(columns)]
    right = []
    for i in range(len(columns)):
        present = [row[i] for row in rows if row[i] is not None]
        right.append(any(_is_number(v) for v in present) and all(_is_number(v) for v in present))

    def line(items):
        padded = (
            text.rjust(width) if flush else text.ljust(width)
            for text, width, flush in zip(items, widths, right, strict=True)
        )
        return " | ".join(padded).rstrip()

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join([line(columns), separator, *(line(row) for row in cells)]) + "\n"


def render_summary(table):
    rows = []
    for name in table.columns:
        try:
            numbers = table.numbers(name)
        except ValueError:
            continue
        s = describe(numbers)
        if s.count:
            rows.append([name, s.count, s.missing, s.mean, s.minimum, s.median, s.maximum, s.stdev])
    if not rows:
        return "No numeric columns.\n"
    return render_table(_SUMMARY_COLUMNS, rows)
