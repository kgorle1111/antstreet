# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: parse_invalid_input.
from functools import cmp_to_key


def parse(version: str) -> tuple[int, int, int, tuple[int | str, ...], tuple[str, ...]]:
    if not isinstance(version, str):
        raise ValueError("Version must be a string")

    if version != version.strip():
        raise ValueError("Version cannot have leading or trailing whitespace")

    if not version:
        raise ValueError("Version cannot be empty")

    if version[0] in ('+', '-', 'v', 'V'):
        raise ValueError("Invalid version format")

    # Split by + to separate build metadata
    if '+' in version:
        parts_list = version.split('+')
        if len(parts_list) != 2:
            raise ValueError("Invalid version format")
        version_part, build_part = parts_list
        if not build_part:
            raise ValueError("Build metadata cannot be empty")
    else:
        version_part = version
        build_part = ""

    # Split by - to separate prerelease
    if '-' in version_part:
        parts_list = version_part.split('-', 1)
        base_part, prerelease_part = parts_list
        if not prerelease_part:
            raise ValueError("Prerelease cannot be empty")
    else:
        base_part = version_part
        prerelease_part = ""

    # Parse major.minor.patch
    parts = base_part.split('.')
    if len(parts) != 3:
        raise ValueError("Version must have exactly three numeric parts")

    # Check for empty parts
    for part in parts:
        if not part:
            raise ValueError("Numeric parts cannot be empty")

    # Validate and convert to integers
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except ValueError:
        raise ValueError("Numeric parts must be valid integers")

    # Check for leading zeros in numeric parts
    for part in parts:
        if len(part) > 1 and part[0] == '0':
            raise ValueError("Numeric parts cannot have leading zeros")

    # Parse prerelease
    prerelease = ()
    if prerelease_part:
        prerelease_ids = prerelease_part.split('.')
        prerelease_list = []
        for id_str in prerelease_ids:
            if not id_str:
                raise ValueError("Empty identifier in prerelease")
            # Check valid characters
            for c in id_str:
                if c not in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-':
                    raise ValueError("Invalid character in identifier")
            # Check if numeric (all digits)
            if id_str.isdigit():
                # Check for leading zeros
                if len(id_str) > 1 and id_str[0] == '0':
                    raise ValueError("Numeric identifier cannot have leading zeros")
                prerelease_list.append(int(id_str))
            else:
                prerelease_list.append(id_str)
        prerelease = tuple(prerelease_list)

    # Parse build metadata
    build = ()
    if build_part:
        build_ids = build_part.split('.')
        build_list = []
        for id_str in build_ids:
            if not id_str:
                raise ValueError("Empty identifier in build metadata")
            # Check valid characters
            for c in id_str:
                if c not in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-':
                    raise ValueError("Invalid character in identifier")
            build_list.append(id_str)
        build = tuple(build_list)

    return (major, minor, patch, prerelease, build)


def compare(a: str, b: str) -> int:
    major_a, minor_a, patch_a, prerelease_a, build_a = parse(a)
    major_b, minor_b, patch_b, prerelease_b, build_b = parse(b)

    # Compare major, minor, patch
    if major_a != major_b:
        return -1 if major_a < major_b else 1
    if minor_a != minor_b:
        return -1 if minor_a < minor_b else 1
    if patch_a != patch_b:
        return -1 if patch_a < patch_b else 1

    # Compare prerelease
    # Version without prerelease > version with prerelease
    if prerelease_a and not prerelease_b:
        return -1
    if not prerelease_a and prerelease_b:
        return 1

    if prerelease_a and prerelease_b:
        # Compare prerelease identifiers
        for i in range(min(len(prerelease_a), len(prerelease_b))):
            id_a = prerelease_a[i]
            id_b = prerelease_b[i]

            is_a_numeric = isinstance(id_a, int)
            is_b_numeric = isinstance(id_b, int)

            if is_a_numeric and is_b_numeric:
                # Both numeric, compare numerically
                if id_a != id_b:
                    return -1 if id_a < id_b else 1
            elif is_a_numeric and not is_b_numeric:
                # Numeric < alphanumeric
                return -1
            elif not is_a_numeric and is_b_numeric:
                # Alphanumeric > numeric
                return 1
            else:
                # Both alphanumeric, compare as strings
                if id_a != id_b:
                    return -1 if id_a < id_b else 1

        # All shared identifiers equal, compare lengths
        if len(prerelease_a) != len(prerelease_b):
            return -1 if len(prerelease_a) < len(prerelease_b) else 1

    # Build metadata is ignored
    return 0


def sort_versions(versions: list[str]) -> list[str]:
    # Validate all versions
    for v in versions:
        parse(v)

    # Sort using the compare function
    return sorted(versions, key=cmp_to_key(compare))
