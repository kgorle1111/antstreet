"""Check that a folder of benchmark tasks is byte-identical to the one that was pre-registered.

    python3 -I scripts/verify_task_set.py DIR --expect DIGEST

Standard library only and it imports nothing from antstreet, so a third party can run it on a
published folder without installing or trusting the project. It prints two values:

  digest  full SHA-256 over every file in DIR (the value that is pre-registered)
  hash    the 16-hex task-set hash recorded in each result cell (scored files only; no mutants)

Exit 0 when the digest equals --expect, 1 when it does not (both are printed), 2 on bad input.
It proves the files are unchanged since registration; it does not prove when any run happened.

Keep in step with task_set_digest / task_set_hash in src/antstreet/bench/tasks.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _feed(digest: hashlib._Hash, rel_posix: str, data: bytes) -> None:
    # Length-prefixed, so where a name ends and its content begins is unambiguous.
    for chunk in (rel_posix.encode(), data):
        digest.update(len(chunk).to_bytes(8, "big") + chunk)


def pool_digest(pool: Path) -> str:
    files: list[tuple[str, Path]] = []
    for path in pool.rglob("*"):
        rel = path.relative_to(pool)
        for part in rel.parts:
            if part == "__pycache__" or part.startswith("."):
                raise ValueError(f"{part!r} found at {path}; remove it and rerun")
        if path.is_symlink():
            raise ValueError(f"symlink found at {path}; remove it and rerun")
        if path.is_file():
            files.append((rel.as_posix(), path))
    digest = hashlib.sha256()
    for rel_posix, path in sorted(files, key=lambda f: f[0].encode()):
        _feed(digest, rel_posix, path.read_bytes())
    return digest.hexdigest()


def set_hash(pool: Path) -> str:
    """Tasks are the subfolders holding meta.json, ordered by the id inside it."""
    tasks = []
    for meta in sorted(pool.glob("*/meta.json")):
        tasks.append((json.loads(meta.read_text())["id"], meta.parent))
    digest = hashlib.sha256()
    for _, root in sorted(tasks, key=lambda t: t[0]):
        mutants = root / "mutants"
        for path in sorted(root.rglob("*")):
            skipped = "__pycache__" in path.parts or path.is_relative_to(mutants)
            if path.is_file() and not skipped:
                _feed(digest, path.relative_to(root.parent).as_posix(), path.read_bytes())
    return digest.hexdigest()[:16]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", type=Path, help="the task folder, e.g. bench/tasks")
    ap.add_argument("--expect", required=True, help="the pre-registered 64-hex digest")
    args = ap.parse_args(argv)
    expect = args.expect.strip().lower()
    if not _HEX64.fullmatch(expect):
        print(f"--expect must be 64 lowercase hex characters, got {args.expect!r}", file=sys.stderr)
        return 2
    if not args.dir.is_dir():
        print(f"{args.dir} is not a directory", file=sys.stderr)
        return 2
    try:
        digest, short = pool_digest(args.dir), set_hash(args.dir)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.dir}: {exc}", file=sys.stderr)
        return 2
    print(f"digest {digest}")
    print(f"hash   {short}")
    if digest == expect:
        print("MATCH")
        return 0
    print(f"MISMATCH: expected digest {expect}, computed {digest}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
