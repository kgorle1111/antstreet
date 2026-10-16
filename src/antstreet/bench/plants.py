"""The planted-check harness core: a boss draft copied into a scratch session, with checks chosen by
seed to be swapped for planted ones, and the answer key kept where the reviewer never looks.

A session is `<out_root>/sessions/<sid>/proj/.boss/runs/<run id>/`, holding the draft's
`term_sheet.json` and `checks/` and nothing else: never the ledger, the logs or an investor key. The
key is `<out_root>/keys/<sid>.json`, mode 0600. Check ids and file names stay the draft's own.

Archived drafts are model output. Their bytes are read (size-capped, symlinks refused), parsed as
JSON and hashed; a check file is parsed for structure by `termsheet.structural_problems` on the
copy, never imported or run here. The source is hashed before and after, and a change is an error.

Plant kinds and their oracles come later (PR 2 of ops/c4-approval-study-2026-10-16/DESIGN.md):
`KINDS` is empty until then, so only a seed that plants nothing can be materialized with it.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import random
import re
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from antstreet.audit import MAX_PARSE_BYTES
from antstreet.bench.tasks import TaskError, load_task
from antstreet.termsheet import (
    _CHECK_FILE_RE,  # the rule the term sheet holds a check file name to
    TermSheet,
    TermSheetError,
    structural_problems,
)

TERM_SHEET = "term_sheet.json"
CHECKS = "checks"
# The cap the auditor reads model-written Python under (audit.MAX_PARSE_BYTES), for every file.
MAX_FILE_BYTES = MAX_PARSE_BYTES
MAX_CHECKS = 64  # kn: far above any archived draft (4-12); raise if a real draft is refused
PLANTS_PER_SESSION = (0, 1, 2)
_RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_TELLTALE = b"plant"  # no reviewer-visible byte may say what the session is


class PlantError(Exception):
    """A session that cannot be made safely; the message says what to change."""


class PlantKind(Protocol):
    """One way to make a check wrong. `plant` returns the new file's bytes; it must use only `rng`
    for its choices so a seed reproduces the session."""

    @property
    def name(self) -> str: ...

    def plant(self, original: bytes, rng: random.Random) -> bytes: ...


KINDS: Mapping[str, PlantKind] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Session:
    sid: str
    project: Path  # the scratch project root a review runs in
    run_dir: Path  # <project>/.boss/runs/<run id>
    key_path: Path  # outside `project`; never shown to the reviewer
    plants: tuple[tuple[str, str], ...]  # (check id, kind name), in the draft's check order


def select_plants(
    check_ids: Sequence[str], kind_names: Sequence[str], rng: random.Random
) -> tuple[tuple[str, str], ...]:
    """Draw k in {0, 1, 2} (capped by the number of checks), then k distinct positions and a kind
    for each. Every draw comes from `rng`, in a fixed order, so one seed gives one selection."""
    k = min(rng.choice(PLANTS_PER_SESSION), len(check_ids))
    if k == 0:
        return ()
    if not kind_names:
        raise PlantError(
            "this seed plants checks but no plant kinds are registered: pass `kinds`, or pick a "
            "seed that plants none"
        )
    positions = sorted(rng.sample(range(len(check_ids)), k))
    names = sorted(kind_names)
    return tuple((check_ids[i], rng.choice(names)) for i in positions)


def materialize(
    source_run_dir: Path,
    task_dir: Path,
    out_root: Path,
    seed: int,
    kinds: Mapping[str, PlantKind] = KINDS,
) -> Session:
    """Copy one archived draft into a new session under `out_root`, plant checks by `seed`, and
    write the key. Raises PlantError, leaving no session and no key, if anything is unsafe."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise PlantError(f"the seed must be an int, got {seed!r}")
    for name, kind in kinds.items():
        if kind.name != name:
            raise PlantError(f"plant kind registered as {name!r} calls itself {kind.name!r}")
    source = _source_dir(source_run_dir)
    root = _out_root(out_root, source)
    try:
        task = load_task(task_dir)
    except TaskError as exc:
        raise PlantError(f"{task_dir} is not a bench task: {exc}") from exc

    before = _digests(source)
    sheet_bytes = _read(source / TERM_SHEET)
    sheet = _sheet(sheet_bytes, source)
    if sheet.idea.strip() != task.idea:
        raise PlantError(
            f"the draft's idea is not the idea.md of task {task.id}: pair {source} with the task "
            "it was drafted for"
        )
    originals = {c.id: _read(_check_path(source, c.file, c.id)) for c in sheet.checks}
    files = {c.id: c.file for c in sheet.checks}
    copied = {TERM_SHEET: _sha(sheet_bytes)} | {
        f"{CHECKS}/{files[i]}": _sha(data) for i, data in originals.items()
    }

    rng = random.Random(seed)
    chosen = select_plants([c.id for c in sheet.checks], list(kinds), rng)
    planted = {i: _planted(kinds[kind], originals[i], i, rng) for i, kind in chosen}

    sid = hashlib.sha256(
        json.dumps({"seed": seed, "source": copied}, sort_keys=True).encode()
    ).hexdigest()[:16]
    session_dir = root / "sessions" / sid
    project = session_dir / "proj"
    run_dir = project / ".boss" / "runs" / source.name
    key_path = root / "keys" / f"{sid}.json"
    for folder in (root / "keys", root / "sessions"):
        # The sid is predictable, so a linked folder could put the key in the reviewer's project.
        if folder.is_symlink():
            raise PlantError(f"{folder} must be a real folder, not a symlink")
    if key_path.exists() or key_path.is_symlink():
        raise PlantError(f"the key {key_path} already exists: use a new out_root or another seed")
    (root / "sessions").mkdir(exist_ok=True)
    _under(root, session_dir)  # a `sessions` symlinked out of out_root is refused here
    try:
        session_dir.mkdir()
    except FileExistsError as exc:
        raise PlantError(
            f"the session {session_dir} already exists: use a new out_root or another seed"
        ) from exc
    try:
        (run_dir / CHECKS).mkdir(parents=True)
        _write_new(_under(root, run_dir / TERM_SHEET), sheet_bytes)
        for check_id, data in originals.items():
            dest = _under(root, run_dir / CHECKS / files[check_id])
            _write_new(dest, planted.get(check_id, data))
        problems = structural_problems(sheet, run_dir / CHECKS)
        if problems:
            raise PlantError(f"the session's term sheet does not validate: {'; '.join(problems)}")
        if _digests(source) != before:
            raise PlantError(f"the source changed while it was copied: {source}; nothing kept")
        key = {
            "schema": 1,
            "seed": seed,
            "session": sid,
            "source": str(source),
            "run_id": source.name,
            "task": task.id,
            "task_dir": str(task_dir.resolve()),
            "source_sha256": copied,
            "plants": [
                {
                    "check_id": i,
                    "kind": kind,
                    "file": files[i],
                    "sha256": _sha(planted[i]),
                    "oracle": None,  # filled by the kind's oracle (PR 2), never by hand
                }
                for i, kind in chosen
            ],
        }
        _write_key(_under(root, key_path), json.dumps(key, indent=2, sort_keys=True) + "\n")
    except BaseException:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise
    return Session(sid, project, run_dir, key_path, chosen)


def _source_dir(path: Path) -> Path:
    if path.is_symlink():
        raise PlantError(f"the source {path} is a symlink: pass the run folder it points to")
    if not path.is_dir():
        raise PlantError(f"the source {path} is not a run folder")
    if not _RUN_ID_RE.match(path.name):
        raise PlantError(f"the source folder name {path.name!r} is not a run id")
    checks = path / CHECKS
    if checks.is_symlink() or not checks.is_dir():
        raise PlantError(f"{checks} must be a real folder, not a symlink or missing")
    return path.resolve()


def _out_root(path: Path, source: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise PlantError(f"out_root {path} must be an existing directory, not a symlink: create it")
    root = path.resolve()
    for folder in (root, *root.parents):
        if (folder / ".git").exists():
            raise PlantError(
                f"out_root {path} is inside the git checkout {folder}: sessions and keys must "
                "never land in a repository; use a scratch folder outside it"
            )
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise PlantError(f"out_root {path} and the source {source} overlap: keep them apart")
    project = source.parent.parent.parent  # <project>/.boss/runs/<id>, as the archive keeps it
    if source.parent.name == "runs" and root.is_relative_to(project):
        raise PlantError(f"out_root {path} is inside the source's project {project}")
    return root


def _under(root: Path, path: Path) -> Path:
    """Every write goes under out_root; anything else is a bug, so it is refused, not fixed."""
    if not path.parent.resolve().is_relative_to(root):
        raise PlantError(f"refusing to write {path}: it is not under out_root {root}")
    return path


def _check_path(source: Path, name: str, check_id: str) -> Path:
    if not _CHECK_FILE_RE.match(name):
        raise PlantError(f"check {check_id} file {name!r} must be named test_<name>.py")
    return source / CHECKS / name


def _sheet(data: bytes, source: Path) -> TermSheet:
    try:
        sheet = TermSheet.from_json(data.decode("utf-8"))
    except (UnicodeDecodeError, TermSheetError) as exc:
        raise PlantError(f"{source / TERM_SHEET} is not a valid term sheet: {exc}") from exc
    if len(sheet.checks) > MAX_CHECKS:
        raise PlantError(f"the draft has {len(sheet.checks)} checks, over {MAX_CHECKS}")
    return sheet


def _planted(kind: PlantKind, original: bytes, check_id: str, rng: random.Random) -> bytes:
    data = kind.plant(original, rng)
    if not isinstance(data, bytes) or data == original:
        raise PlantError(f"plant kind {kind.name} left check {check_id} unchanged")
    if len(data) > MAX_FILE_BYTES:
        raise PlantError(
            f"plant kind {kind.name} made check {check_id} over {MAX_FILE_BYTES} bytes"
        )
    if _TELLTALE in data.lower() and _TELLTALE not in original.lower():
        raise PlantError(f"plant kind {kind.name} wrote 'plant' into check {check_id}")
    return data


def _open(path: Path) -> int:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PlantError(f"{path} is a symlink: copy only real files") from exc
        raise PlantError(f"cannot read {path}: {exc.strerror}") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise PlantError(f"{path} is not a regular file")
    return fd


def _read(path: Path) -> bytes:
    with os.fdopen(_open(path), "rb") as fh:
        data = fh.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise PlantError(f"{path} is over {MAX_FILE_BYTES} bytes: not a draft this harness copies")
    return data


def _digests(source: Path) -> dict[str, str]:
    """sha256 of every regular file in the run folder and its checks (ledger included: it is hashed,
    never copied), so a write to any of them during a session is seen."""
    found: dict[str, str] = {}
    for folder in (source, source / CHECKS):
        for entry in sorted(os.scandir(folder), key=lambda e: e.name):
            if entry.is_file(follow_symlinks=False):
                digest = hashlib.sha256()
                with os.fdopen(_open(Path(entry.path)), "rb") as fh:
                    while chunk := fh.read(1 << 20):
                        digest.update(chunk)
                found[Path(entry.path).relative_to(source).as_posix()] = digest.hexdigest()
    return found


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _write_key(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, exist_ok=True)
    if path.parent.is_symlink():  # created by someone else since the check in materialize
        raise PlantError(f"{path.parent} must be a real folder, not a symlink")
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
