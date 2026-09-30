Create a Python module `semver.py` (standard library only) implementing Semantic Versioning 2.0.0 with three functions:

    parse(version: str) -> tuple[int, int, int, tuple[int | str, ...], tuple[str, ...]]
    compare(a: str, b: str) -> int
    sort_versions(versions: list[str]) -> list[str]

Parsing:

1. A valid version is `MAJOR.MINOR.PATCH`, optionally followed by `-` and a prerelease, optionally followed by `+` and build metadata, for example `1.2.3`, `1.2.3-rc.1`, `1.2.3+20130313`, `1.2.3-rc.1+build.5`. There are exactly three dot-separated numeric parts.
2. A numeric part is one or more ASCII digits (0-9) with no leading zeros; the part `0` alone is fine (`0.0.0` is valid, `01.2.3` is not). There is no upper bound on its size.
3. The prerelease starts at the first `-` after the patch part and ends at the first `+` or the end of the string. Build metadata starts at the first `+`. Both are lists of identifiers separated by dots. An identifier may itself contain hyphens, so `1.0.0-alpha-beta` has the single prerelease identifier `alpha-beta`, and `1.0.0+build-1` has the single build identifier `build-1`.
4. An identifier is one or more characters from `0-9`, `A-Z`, `a-z` and `-`. An empty identifier is invalid: a `-` or `+` with nothing after it (`1.2.3-`, `1.2.3+`) and empty items such as `1.2.3-a..b` or `1.2.3-.a` are all invalid. Any other character is invalid, including spaces, underscores and every non-ASCII character (non-ASCII digits included).
5. A prerelease identifier made only of ASCII digits is numeric and must not have leading zeros (`1.2.3-0` is valid, `1.2.3-01` is not). An identifier that contains any letter or hyphen is alphanumeric and may start with zeros (`1.2.3-0a`, `1.2.3-01a` are valid). Build identifiers may always have leading zeros (`1.2.3+001` is valid).
6. `parse` returns `(major, minor, patch, prerelease, build)`. The first three are ints. `prerelease` is a tuple of identifiers in order: numeric identifiers as ints, alphanumeric identifiers as strings; it is the empty tuple when there is no prerelease. `build` is a tuple of strings exactly as written (`"001"` stays `"001"`); it is the empty tuple when there is no build metadata. Example: `parse("1.2.3-alpha.7+exp.sha.5")` returns `(1, 2, 3, ("alpha", 7), ("exp", "sha", "5"))`.
7. `parse` raises `ValueError` for anything invalid: missing parts (`1`, `1.2`, `1.2.`, `1..3`, the empty string), extra numeric parts (`1.2.3.4`), leading zeros as described above, empty identifiers, illegal characters, a leading `v` or `V`, a sign (`+1.2.3`, `-1.2.3`), any leading or trailing whitespace (including a trailing newline), and any argument that is not a `str` (`None`, an int, `bytes`, a list). Non-string input raises `ValueError`, not `TypeError`.

Comparing:

8. `compare(a, b)` parses both arguments (so invalid input raises `ValueError`) and returns the int `-1` if `a` has lower precedence than `b`, `0` if equal precedence, `1` if higher.
9. Precedence compares major, then minor, then patch, each numerically (`1.10.0` is higher than `1.9.0`).
10. If major, minor and patch are equal, a version with a prerelease has lower precedence than the same version without one (`1.0.0-rc.1` is lower than `1.0.0`).
11. If both have a prerelease, compare the identifiers left to right. Two numeric identifiers compare numerically. A numeric identifier is lower than an alphanumeric one. Two alphanumeric identifiers compare as strings in ASCII order (uppercase letters before lowercase letters, `-` before digits and letters). If all shared identifiers are equal, the prerelease with more identifiers is higher. Example order: `1.0.0-alpha` < `1.0.0-alpha.1` < `1.0.0-alpha.beta` < `1.0.0-beta` < `1.0.0-beta.2` < `1.0.0-beta.11` < `1.0.0-rc.1` < `1.0.0`.
12. Build metadata is ignored: versions that differ only in build metadata have equal precedence, so `compare` returns `0`.

Sorting:

13. `sort_versions(versions)` returns a new list of the same strings in ascending order of precedence. The input list is not modified and the result is a different list object. The sort is stable: versions of equal precedence (which can only differ in build metadata) keep their relative input order. An empty list gives an empty list. If any element is invalid, `ValueError` is raised.
