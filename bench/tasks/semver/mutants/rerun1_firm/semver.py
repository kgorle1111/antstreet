# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: parse_invalid_input.
from functools import cmp_to_key


def parse(version: str) -> tuple[int, int, int, tuple[int | str, ...], tuple[str, ...]]:
    if not isinstance(version, str):
        raise ValueError("Input must be a string")

    if version != version.strip():
        raise ValueError("Leading or trailing whitespace")

    if version.startswith('v') or version.startswith('V'):
        raise ValueError("Leading v or V")

    if version.startswith('+') or version.startswith('-'):
        raise ValueError("Leading sign")

    if '+' in version:
        parts_split = version.split('+')
        if len(parts_split) != 2:
            raise ValueError("Multiple + not allowed")
        version_and_prerelease = parts_split[0]
        build_part = parts_split[1]
    else:
        version_and_prerelease = version
        build_part = None

    if '-' in version_and_prerelease:
        parts_split = version_and_prerelease.split('-', 1)
        numeric_part = parts_split[0]
        prerelease_part = parts_split[1]
    else:
        numeric_part = version_and_prerelease
        prerelease_part = None

    numeric_parts = numeric_part.split('.')
    if len(numeric_parts) != 3:
        raise ValueError("Invalid format")

    major_str, minor_str, patch_str = numeric_parts

    if not major_str or not minor_str or not patch_str:
        raise ValueError("Empty numeric part")

    if not all(c.isdigit() for c in major_str) or not all(c.isdigit() for c in minor_str) or not all(c.isdigit() for c in patch_str):
        raise ValueError("Non-digit in numeric part")

    major = int(major_str)
    minor = int(minor_str)
    patch = int(patch_str)

    if (major_str != '0' and major_str.startswith('0')) or (minor_str != '0' and minor_str.startswith('0')) or (patch_str != '0' and patch_str.startswith('0')):
        raise ValueError("Leading zero in numeric part")

    prerelease = ()
    if prerelease_part is not None:
        if prerelease_part == '':
            raise ValueError("Empty prerelease")
        prerelease_identifiers = prerelease_part.split('.')
        prerelease_list = []
        for identifier in prerelease_identifiers:
            if identifier == '':
                raise ValueError("Empty identifier")
            if not all(c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-' for c in identifier):
                raise ValueError("Invalid character")
            if identifier.isdigit():
                if identifier != '0' and identifier.startswith('0'):
                    raise ValueError("Leading zero in numeric identifier")
                prerelease_list.append(int(identifier))
            else:
                prerelease_list.append(identifier)
        prerelease = tuple(prerelease_list)

    build = ()
    if build_part is not None:
        if build_part == '':
            raise ValueError("Empty build")
        build_identifiers = build_part.split('.')
        build_list = []
        for identifier in build_identifiers:
            if identifier == '':
                raise ValueError("Empty identifier")
            if not all(c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-' for c in identifier):
                raise ValueError("Invalid character")
            build_list.append(identifier)
        build = tuple(build_list)

    return (major, minor, patch, prerelease, build)


def compare(a: str, b: str) -> int:
    major_a, minor_a, patch_a, prerelease_a, _ = parse(a)
    major_b, minor_b, patch_b, prerelease_b, _ = parse(b)

    if major_a != major_b:
        return -1 if major_a < major_b else 1
    if minor_a != minor_b:
        return -1 if minor_a < minor_b else 1
    if patch_a != patch_b:
        return -1 if patch_a < patch_b else 1

    if prerelease_a and not prerelease_b:
        return -1
    if not prerelease_a and prerelease_b:
        return 1
    if not prerelease_a and not prerelease_b:
        return 0

    for i in range(min(len(prerelease_a), len(prerelease_b))):
        id_a = prerelease_a[i]
        id_b = prerelease_b[i]

        is_num_a = isinstance(id_a, int)
        is_num_b = isinstance(id_b, int)

        if is_num_a and is_num_b:
            if id_a != id_b:
                return -1 if id_a < id_b else 1
        elif is_num_a:
            return -1
        elif is_num_b:
            return 1
        else:
            if id_a != id_b:
                return -1 if id_a < id_b else 1

    if len(prerelease_a) != len(prerelease_b):
        return -1 if len(prerelease_a) < len(prerelease_b) else 1

    return 0


def sort_versions(versions: list[str]) -> list[str]:
    parsed = [(v, parse(v)) for v in versions]

    def cmp(a_tuple, b_tuple):
        a_str, (major_a, minor_a, patch_a, prerelease_a, _) = a_tuple
        b_str, (major_b, minor_b, patch_b, prerelease_b, _) = b_tuple

        if major_a != major_b:
            return -1 if major_a < major_b else 1
        if minor_a != minor_b:
            return -1 if minor_a < minor_b else 1
        if patch_a != patch_b:
            return -1 if patch_a < patch_b else 1

        if prerelease_a and not prerelease_b:
            return -1
        if not prerelease_a and prerelease_b:
            return 1
        if not prerelease_a and not prerelease_b:
            return 0

        for i in range(min(len(prerelease_a), len(prerelease_b))):
            id_a = prerelease_a[i]
            id_b = prerelease_b[i]

            is_num_a = isinstance(id_a, int)
            is_num_b = isinstance(id_b, int)

            if is_num_a and is_num_b:
                if id_a != id_b:
                    return -1 if id_a < id_b else 1
            elif is_num_a:
                return -1
            elif is_num_b:
                return 1
            else:
                if id_a != id_b:
                    return -1 if id_a < id_b else 1

        if len(prerelease_a) != len(prerelease_b):
            return -1 if len(prerelease_a) < len(prerelease_b) else 1

        return 0

    sorted_parsed = sorted(parsed, key=cmp_to_key(cmp))
    return [v for v, _ in sorted_parsed]
