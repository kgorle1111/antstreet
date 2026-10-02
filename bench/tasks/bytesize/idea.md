Create a Python module `bytesize.py` (standard library only) with two functions:

    parse_size(text: str) -> int
    format_size(n: int, binary: bool = True) -> str

`parse_size` turns strings such as `1.5 KiB`, `2MB`, `512` and `10 gib` into a number of bytes.
`format_size` turns a number of bytes into a short human-readable string.

Parsing:

1. The text is a number, optionally followed by a unit. Spaces and tabs may appear between the
   number and the unit (`1.5 KiB`, `1.5KiB` and `1.5 \t KiB` are the same), and whitespace may
   surround the whole text. With no unit the number is a count of bytes: `512` is 512.
2. A number is one or more ASCII digits 0-9, optionally followed by a `.` and one or more digits.
   `.5`, `5.`, `1.5.5`, `1,5`, `1e3`, `1_000`, a sign (`-1 KB` and `+1 KB` are both invalid),
   and non-ASCII digits are not numbers. Digits with a space inside (`1 000 KB`) are invalid.
3. Units are case-insensitive, so `kib`, `KIB` and `KiB` are the same unit. The decimal units are
   `KB`, `MB`, `GB`, `TB` and `PB`, which are 1000, 1000**2, 1000**3, 1000**4 and 1000**5 bytes.
   The binary units are `KiB`, `MiB`, `GiB`, `TiB` and `PiB`, which are 1024, 1024**2, 1024**3,
   1024**4 and 1024**5 bytes. `B` is one byte. The single letters `K`, `M`, `G`, `T` and `P` are
   short for the binary units, so `1K` is 1024. `Kb` is the same as `KB` (1000), not kilobits.
4. The result is an `int`. The number times the unit size is computed exactly, and when it is not a
   whole number of bytes it is rounded to the nearest byte, with a half rounding up: `1.5 B` is 2,
   `2.5 B` is 3, `0.5 B` is 1, `0.4 B` is 0 and `0.1 KiB` (102.4 bytes) is 102. Large values are
   exact: `9007199254740993` is 9007199254740993 and `123456789.123456789 GB` is
   123456789123456789.
5. `parse_size` raises `ValueError` for anything else: the empty string or only whitespace, a unit
   without a number (`KB`), an unknown unit (`1 XB`, `1 Ki`, `1 KBB`, `1 kilobyte`, `1 bytes`), a
   unit with a space inside (`1 K B`), anything after the unit, and any other characters. Input
   that is not a `str` (an int, a float, None, bytes) raises `TypeError`.

Formatting:

6. `format_size` takes an int `n` of zero or more. A negative `n` raises `ValueError`, and an `n`
   that is not an `int` (a float, a str, None, or a `bool`) raises `TypeError`.
7. With `binary=True` the units are `B`, `KiB`, `MiB`, `GiB`, `TiB`, `PiB` and the step is 1024.
   With `binary=False` they are `B`, `KB`, `MB`, `GB`, `TB`, `PB` and the step is 1000. The unit is
   the largest one whose size is at most `n`; below one step the result is just the byte count:
   `0` is `0 B`, `1023` is `1023 B`, `1024` is `1 KiB`, and with `binary=False` `999` is `999 B`
   and `1000` is `1 KB`. There is no unit above PiB or PB: 1024**6 is `1024 PiB`.
8. The number shown is `n` divided by the unit size, rounded to one decimal digit, a half rounding
   up (exactly, not through binary floating point), and written without the decimal when it is
   zero: 1536 is `1.5 KiB`, 2048 is `2 KiB`, 1280 is `1.3 KiB` (exactly 1.25), and with
   `binary=False` 1050 is `1.1 KB`, 1150 is `1.2 KB` and 1950 is `2 KB`. A byte count is written
   as a plain integer with no decimal.
9. If the rounded number reaches the step (1024, or 1000 with `binary=False`) the next larger unit
   is used instead, and the number is worked out again from that unit, so 1048575 is `1 MiB` and
   not `1024 KiB`, and 999950 with `binary=False` is `1 MB`. Just below that boundary the lower
   unit stays: 1048524 is `1023.9 KiB`.
10. The number and the unit are separated by a single space, and the result is a `str`. Large
    values are exact; there is no limit on `n`.
