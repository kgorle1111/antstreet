"""Held-out checks: pytest files the workers never see, graded once, on the assembled product.

They live in the run folder's `held_out/`, beside `checks/` and never inside a workspace or
`product/`. `manifest.json` names each check (an id `h01`.., its file, and the quote of the idea it
verifies). The investor approves the folder's content hashes with the term sheet, so a file edited
afterwards voids the approval exactly as an edited visible check does (`approval.require_approval`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from boss.gate import Check
from boss.termsheet import CheckSpec, check_file_problems, empty_checks_problems

SCOPE = "held_out"  # the `scope` of a held-out `check_result` event
MAX_HELD_OUT = 8  # each is a pytest run on the product, and the investor reads every one
MANIFEST = "manifest.json"
_ID = re.compile(r"h\d{2}\Z")


class HeldOutError(Exception):
    """The held-out folder is not readable as a manifest and its files."""


@dataclass(frozen=True, slots=True)
class HeldOutCheck:
    id: str
    file: str
    source: str  # a fragment of the idea, word for word: what this check verifies

    def to_check(self) -> Check:
        return Check(self.id, self.file)

    def spec(self) -> CheckSpec:
        return CheckSpec(self.id, self.source, self.file, SCOPE)


def file_name(check_id: str) -> str:
    return f"test_{check_id}.py"


def write(directory: Path, entries: Sequence[tuple[HeldOutCheck, str]]) -> None:
    """Write each check's code and the manifest into `directory` (created if missing)."""
    directory.mkdir(parents=True, exist_ok=True)
    for check, code in entries:
        (directory / check.file).write_text(code, encoding="utf-8")
    listed = [{"id": c.id, "file": c.file, "source": c.source} for c, _ in entries]
    (directory / MANIFEST).write_text(json.dumps({"checks": listed}, indent=2), encoding="utf-8")


def load(directory: Path) -> list[HeldOutCheck]:
    """The checks the manifest lists; empty when the run has none. HeldOutError if unreadable."""
    path = directory / MANIFEST
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [HeldOutCheck(str(c["id"]), str(c["file"]), str(c["source"])) for c in raw["checks"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HeldOutError(f"{MANIFEST} is not a held-out manifest: {exc}") from exc


def hashes(directory: Path) -> dict[str, str]:
    """What the investor approves: a hash of every file in the folder. Empty for no folder."""
    if not directory.is_dir():
        return {}
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def id_problems(ids: Sequence[str], taken_ids: Collection[str] = ()) -> list[str]:
    """Ids must look like h01, be unique, and not be a visible check's."""
    problems = [f"held-out check id {i!r} must look like h01" for i in ids if not _ID.match(i)]
    problems += [f"duplicate held-out check id {i!r}" for i, n in Counter(ids).items() if n > 1]
    problems += [
        f"held-out check id {i!r} is also a visible check's id" for i in ids if i in taken_ids
    ]
    return problems


def structure_problems(directory: Path, taken_ids: Collection[str] = ()) -> list[str]:
    """Everything wrong with the folder short of running a check: the manifest, the ids (`h01`..,
    unique, not a visible check's), each file's name, syntax and test function, and any file the
    manifest does not list."""
    try:
        checks = load(directory)
    except HeldOutError as exc:
        return [str(exc)]
    if not checks:
        return ["no held-out checks are listed"] if hashes(directory) else []
    problems = id_problems([c.id for c in checks], taken_ids)
    for check in checks:
        if check.file != file_name(check.id):
            problems.append(f"held-out check {check.id} file must be {file_name(check.id)}")
        else:
            problems += check_file_problems(check.spec(), directory)
    listed = {MANIFEST, *(c.file for c in checks)}
    problems += [f"{name} is in the folder but not in the manifest" for name in hashes(directory)
                 if name not in listed]  # fmt: skip
    return problems


def empty_problems(directory: Path) -> list[str]:
    """A held-out check that passes on an empty workspace cannot tell a product from nothing."""
    return empty_checks_problems([c.to_check() for c in load(directory)], directory)


def problems(directory: Path, taken_ids: Collection[str] = ()) -> list[str]:
    """`structure_problems`, then (only if there are none) the empty-workspace run."""
    return structure_problems(directory, taken_ids) or empty_problems(directory)
