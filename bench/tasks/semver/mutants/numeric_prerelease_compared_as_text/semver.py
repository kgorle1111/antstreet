# Numeric prerelease identifiers compare as text, so beta.11 sorts below beta.2.
import re

_NUM = r"(?:0|[1-9][0-9]*)"
_ID = r"[0-9A-Za-z-]+"
_VERSION = re.compile(
    rf"({_NUM})\.({_NUM})\.({_NUM})(?:-({_ID}(?:\.{_ID})*))?(?:\+({_ID}(?:\.{_ID})*))?"
)


def _prerelease_id(ident: str) -> int | str:
    if not ident.isdigit():
        return ident
    if len(ident) > 1 and ident[0] == "0":
        raise ValueError(f"numeric prerelease identifier with leading zero: {ident!r}")
    return int(ident)


def parse(version: str) -> tuple[int, int, int, tuple[int | str, ...], tuple[str, ...]]:
    if not isinstance(version, str):
        raise ValueError(f"version must be a string, got {type(version).__name__}")
    match = _VERSION.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid version: {version!r}")
    major, minor, patch, pre, build = match.groups()
    prerelease = tuple(_prerelease_id(i) for i in pre.split(".")) if pre else ()
    return int(major), int(minor), int(patch), prerelease, tuple(build.split(".")) if build else ()


def _key(version: str) -> tuple:
    major, minor, patch, prerelease, _ = parse(version)
    # A release sorts above any prerelease of the same core; numeric ids sort below alphanumeric.
    ids = tuple((0, str(i), "") if isinstance(i, int) else (1, "", i) for i in prerelease)
    return major, minor, patch, not prerelease, ids


def compare(a: str, b: str) -> int:
    ka, kb = _key(a), _key(b)
    return (ka > kb) - (ka < kb)


def sort_versions(versions: list[str]) -> list[str]:
    return sorted(versions, key=_key)
