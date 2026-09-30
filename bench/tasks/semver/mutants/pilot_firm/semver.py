# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: parse_invalid_input.
from functools import cmp_to_key


def parse(version: str) -> tuple[int, int, int, tuple[int | str, ...], tuple[str, ...]]:
    """Parse a semantic version string according to Semantic Versioning 2.0.0.

    Returns (major, minor, patch, prerelease_tuple, build_tuple).
    Raises ValueError for invalid input.
    """
    if not isinstance(version, str):
        raise ValueError("Version must be a string")

    if any(c.isspace() for c in version):
        raise ValueError("Version contains whitespace")

    # Split by '+' to get build metadata
    build_tuple = ()
    if '+' in version:
        version, build_part = version.split('+', 1)
        if not build_part:
            raise ValueError("Empty build metadata")

        build_ids = build_part.split('.')
        build_list = []
        for id_str in build_ids:
            if not id_str:
                raise ValueError("Empty build identifier")
            if not all(c.isalnum() or c == '-' for c in id_str):
                raise ValueError("Invalid characters in build")
            build_list.append(id_str)
        build_tuple = tuple(build_list)

    # Split by '-' to get prerelease
    prerelease_tuple = ()
    if '-' in version:
        version, prerelease_part = version.split('-', 1)
        if not prerelease_part:
            raise ValueError("Empty prerelease")

        prerelease_ids = prerelease_part.split('.')
        prerelease_list = []
        for id_str in prerelease_ids:
            if not id_str:
                raise ValueError("Empty prerelease identifier")
            if not all(c.isalnum() or c == '-' for c in id_str):
                raise ValueError("Invalid characters in prerelease")
            if id_str.isdigit():
                if len(id_str) > 1 and id_str[0] == '0':
                    raise ValueError("Leading zeros not allowed")
                prerelease_list.append(int(id_str))
            else:
                prerelease_list.append(id_str)
        prerelease_tuple = tuple(prerelease_list)

    # Parse version part (MAJOR.MINOR.PATCH)
    parts = version.split('.')
    if len(parts) != 3:
        raise ValueError("Version must have exactly 3 parts")

    try:
        major_str, minor_str, patch_str = parts
        major = int(major_str)
        minor = int(minor_str)
        patch = int(patch_str)
    except ValueError:
        raise ValueError("Major, minor, patch must be integers")

    # Check for leading zeros
    for p_str, p_val in zip(parts, [major, minor, patch]):
        if p_str != str(p_val):
            raise ValueError("Leading zeros not allowed")

    return (major, minor, patch, prerelease_tuple, build_tuple)


def compare(a: str, b: str) -> int:
    """Compare two semantic versions.

    Returns -1 if a < b, 0 if equal, 1 if a > b.
    Raises ValueError if either version is invalid.
    """
    a_parsed = parse(a)
    b_parsed = parse(b)

    a_major, a_minor, a_patch, a_pre, a_build = a_parsed
    b_major, b_minor, b_patch, b_pre, b_build = b_parsed

    # Compare major, minor, patch
    if a_major != b_major:
        return -1 if a_major < b_major else 1
    if a_minor != b_minor:
        return -1 if a_minor < b_minor else 1
    if a_patch != b_patch:
        return -1 if a_patch < b_patch else 1

    # Compare prerelease (build metadata is ignored)
    has_a_pre = len(a_pre) > 0
    has_b_pre = len(b_pre) > 0

    if has_a_pre and not has_b_pre:
        return -1
    if not has_a_pre and has_b_pre:
        return 1
    if not has_a_pre and not has_b_pre:
        return 0

    # Both have prerelease
    for a_id, b_id in zip(a_pre, b_pre):
        a_is_num = isinstance(a_id, int)
        b_is_num = isinstance(b_id, int)

        if a_is_num and not b_is_num:
            return -1
        if not a_is_num and b_is_num:
            return 1

        if a_id != b_id:
            return -1 if a_id < b_id else 1

    # Longer prerelease > shorter
    if len(a_pre) != len(b_pre):
        return -1 if len(a_pre) < len(b_pre) else 1

    return 0


def sort_versions(versions: list[str]) -> list[str]:
    """Sort a list of semantic versions in ascending order.

    Returns a new sorted list. Raises ValueError if any version is invalid.
    Stable sort preserves order of equal versions.
    """
    for v in versions:
        parse(v)

    result = versions[:]
    result.sort(key=cmp_to_key(compare))
    return result
