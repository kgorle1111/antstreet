# Same as the reference; the bug is in stats.py: stdev divides by count instead of count - 1
# (population, not sample, deviation).
import csv
import io
import math
import re
from dataclasses import dataclass

_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class Table:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def column(self, name):
        try:
            index = self.columns.index(name)
        except ValueError:
            raise KeyError(name) from None
        return [row[index] for row in self.rows]

    def numbers(self, name):
        numbers = []
        for line, value in enumerate(self.column(name), 1):
            text = value.strip()
            if not text:
                numbers.append(None)
                continue
            number = float(text) if _NUMBER.fullmatch(text) else math.nan
            if not math.isfinite(number):
                raise ValueError(f"column {name!r}, row {line}: not a finite number: {value!r}")
            numbers.append(number)
        return numbers

    def __len__(self):
        return len(self.rows)


def read_table(text):
    if not isinstance(text, str):
        raise ValueError("text must be a str")
    try:
        reader = csv.reader(io.StringIO(text.removeprefix("﻿"), newline=""), strict=True)
        records = [record for record in reader if record]
    except csv.Error as exc:
        raise ValueError(f"bad CSV: {exc}") from exc
    if not records:
        raise ValueError("no header row")
    header = tuple(name.strip() for name in records[0])
    if "" in header or len(set(header)) != len(header):
        raise ValueError("header names must be non-empty and different")
    for number, record in enumerate(records[1:], 1):
        if len(record) != len(header):
            raise ValueError(f"row {number} has {len(record)} fields, expected {len(header)}")
    return Table(header, tuple(tuple(record) for record in records[1:]))
