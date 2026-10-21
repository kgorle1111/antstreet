"""The planted-check harness core: a boss draft copied into a scratch session, with checks chosen by
seed to be swapped for planted ones, and the answer key kept where the reviewer never looks.

A session is `<out_root>/sessions/<sid>/proj/.boss/runs/<run id>/`, holding the draft's
`term_sheet.json` and `checks/` and nothing else: never the ledger, the logs or an investor key. The
key is `<out_root>/keys/<sid>.json`, mode 0600. Check ids and file names stay the draft's own.

Archived drafts are model output. Their bytes are read (size-capped, symlinks refused), parsed as
JSON and hashed; a check file is parsed on the copy, and run only by the sandboxed gate (oracles,
`termsheet.validate`), never imported or run in this process. The source is hashed before and
after, and a change is an error.

A planted check is kept only if its kind's oracle holds (`plant_kinds`: the gate shows the check
is wrong in the way the kind claims); otherwise the kind draws again, up to MAX_ATTEMPTS, and
then the check stays as drafted and the key says the kind was inapplicable. The session is then
validated the way approval validates it (`termsheet.validate`, approval.py `_load_valid`), and a
plant approval would refuse is put back to the draft's check and recorded as caught (T08 when the
empty-workspace run refuses it), never shown.
"""

from __future__ import annotations

import ast
import errno
import hashlib
import io
import json
import os
import random
import re
import shutil
import stat
import tokenize
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from antstreet.audit import MAX_PARSE_BYTES
from antstreet.bench.plant_kinds import (
    Inapplicable,
    OracleResult,
    UnderSpecified,
    Vacuous,
    WrongValue,
)
from antstreet.bench.tasks import BenchTask, TaskError, load_task
from antstreet.termsheet import (
    _CHECK_FILE_RE,  # the rule the term sheet holds a check file name to
    TermSheet,
    TermSheetError,
    validate,
)

TERM_SHEET = "term_sheet.json"
CHECKS = "checks"
# The cap the auditor reads model-written Python under (audit.MAX_PARSE_BYTES), for every file.
MAX_FILE_BYTES = MAX_PARSE_BYTES
MAX_CHECKS = 64  # kn: far above any archived draft (4-12); raise if a real draft is refused
PLANTS_PER_SESSION = (0, 1, 2)
_RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
# No reviewer-visible byte a kind adds may say what the session is, or what was done to a check.
_HINTS = (b"plant", b"vacuous", b"oracle", b"mutant", b"stub", b"perturb", b"under_spec", b"wrong")
MAX_ATTEMPTS = 12  # draws per planted check before the kind is called inapplicable for it


class PlantError(Exception):
    """A session that cannot be made safely; the message says what to change."""


class PlantKind(Protocol):
    """One way to make a check wrong. `plant` returns the new file's bytes, or raises
    `plant_kinds.Inapplicable`; it must use only `rng` for its choices so a seed reproduces the
    session. `oracle` says, from gate runs only, whether `planted` is wrong the way the kind
    claims, or raises `Inapplicable` when the draft's own check leaves nothing to show (no draw
    could hold); it must give the same answer for the same inputs."""

    @property
    def name(self) -> str: ...

    def plant(self, original: bytes, rng: random.Random) -> bytes: ...

    def oracle(
        self, original: bytes, planted: bytes, file: str, task: BenchTask
    ) -> OracleResult: ...


KINDS: Mapping[str, PlantKind] = MappingProxyType(
    {k.name: k for k in (WrongValue(), Vacuous(), UnderSpecified())}
)


@dataclass(frozen=True, slots=True)
class Outcome:
    """One planted check's fate: `data` is the planted file, None when no draw passed the oracle."""

    data: bytes | None
    oracle: OracleResult
    attempts: int


@dataclass(frozen=True, slots=True)
class Session:
    sid: str
    project: Path  # the scratch project root a review runs in
    run_dir: Path  # <project>/.boss/runs/<run id>
    key_path: Path  # outside `project`; never shown to the reviewer
    # (check id, kind name) of the plants the reviewer sees, in the draft's check order; the key
    # also lists the inapplicable and caught ones.
    plants: tuple[tuple[str, str], ...]


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
    # One draw from the session rng per plant: how many draws a kind needs before its oracle holds
    # cannot shift the choices made for the next plant.
    subs = {i: random.Random(rng.getrandbits(64)) for i, _ in chosen}
    outcomes = {
        i: plant_one(kinds[kind], originals[i], files[i], task, subs[i], check_id=i)
        for i, kind in chosen
    }
    planted = {i: o.data for i, o in outcomes.items() if o.data is not None}
    caught: dict[str, str] = {}

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
        problems = _approval_problems(sheet, run_dir / CHECKS)
        # Approval would refuse these: put the draft's checks back and record the catch. Again
        # until none is blamed, since a structural refusal hides the empty-workspace run.
        while blamed := {
            i: mine
            for i in planted
            if i not in caught and (mine := [p for p in problems if p.startswith(f"check {i} ")])
        }:
            for check_id, mine in blamed.items():
                empty = any("empty workspace" in p for p in mine)
                caught[check_id] = "T08" if empty else "validate"
                _rewrite(_under(root, run_dir / CHECKS / files[check_id]), originals[check_id])
            problems = _approval_problems(sheet, run_dir / CHECKS)
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
                    "status": _status(i, planted, caught),
                    "caught_by": caught.get(i),
                    "sha256": _sha(planted[i]) if i in planted else None,
                    "oracle": {
                        "holds": outcomes[i].oracle.holds,
                        "detail": outcomes[i].oracle.detail,
                        "attempts": outcomes[i].attempts,
                    },
                }
                for i, kind in chosen
            ],
        }
        _write_key(_under(root, key_path), json.dumps(key, indent=2, sort_keys=True) + "\n")
    except BaseException:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise
    shown = tuple((i, kind) for i, kind in chosen if i in planted and i not in caught)
    return Session(sid, project, run_dir, key_path, shown)


def plant_one(
    kind: PlantKind,
    original: bytes,
    file: str,
    task: BenchTask,
    rng: random.Random,
    check_id: str = "",
) -> Outcome:
    """Draw plants of `kind` for one check until its oracle holds, at most MAX_ATTEMPTS draws (a
    draw seen before is not judged again). Same rng state, same gate: same outcome."""
    if not _CHECK_FILE_RE.match(file):  # oracles write it into temp folders by this name
        raise PlantError(f"check file {file!r} must be named test_<name>.py")
    seen: set[bytes] = set()
    last = OracleResult(False, "no draw was judged")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = kind.plant(original, rng)
        except Inapplicable as exc:
            return Outcome(None, OracleResult(False, f"inapplicable: {exc}"), attempt)
        data = _planted(kind, original, data, check_id or file)
        if data in seen:
            continue
        seen.add(data)
        try:
            last = kind.oracle(original, data, file, task)
        except Inapplicable as exc:  # the draft's own check leaves nothing to show
            return Outcome(None, OracleResult(False, f"inapplicable: {exc}"), attempt)
        if last.holds:
            return Outcome(data, last, attempt)
    return Outcome(None, last, MAX_ATTEMPTS)


def _status(check_id: str, planted: Mapping[str, bytes], caught: Mapping[str, str]) -> str:
    if check_id in caught:
        return "caught"
    return "shown" if check_id in planted else "inapplicable"


def _approval_problems(sheet: TermSheet, checks_dir: Path) -> list[str]:
    """What approval says of this sheet and these files: `termsheet.validate`, the call
    approval.py `_load_valid` makes before an investor may approve (structure, then every check on
    an empty workspace: T08)."""
    try:
        validate(sheet, checks_dir)
    except TermSheetError as exc:
        return list(exc.problems)
    return []


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


def _planted(kind: PlantKind, original: bytes, data: bytes, check_id: str) -> bytes:
    if not isinstance(data, bytes) or data == original:
        raise PlantError(f"plant kind {kind.name} left check {check_id} unchanged")
    if len(data) > MAX_FILE_BYTES:
        raise PlantError(
            f"plant kind {kind.name} made check {check_id} over {MAX_FILE_BYTES} bytes"
        )
    for word in _HINTS:
        if word in data.lower() and word not in original.lower():
            raise PlantError(
                f"plant kind {kind.name} wrote {word.decode()!r} into check {check_id}"
            )
    added = _comments(data, kind.name, check_id) - _comments(original, kind.name, check_id)
    if added:
        raise PlantError(f"plant kind {kind.name} added the comment {min(added)!r} to {check_id}")
    return data


def _comments(data: bytes, kind: str, check_id: str) -> set[str]:
    """The check's comments, by the tokenizer. A plant that is not Python is a kind's bug."""
    try:
        ast.parse(data)
        tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
    except (SyntaxError, ValueError, tokenize.TokenError) as exc:
        raise PlantError(f"plant kind {kind} made check {check_id} unparseable: {exc}") from exc
    return {t.string for t in tokens if t.type == tokenize.COMMENT}


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


def _rewrite(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
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
