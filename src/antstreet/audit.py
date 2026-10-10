"""`antstreet audit plan`: seal checks for a change request before anyone's work is looked at.

The audit store lives outside the repository (`~/.boss-audit`, or `$BOSS_AUDIT_HOME`): the checks
are not in the audited repo, in an agent's prompt or in its working folder. The store has the layout
of a project (`<store>/.boss/runs/<id>`, `<store>/.boss/investor.key`), so the run's ledger, the
investor's signed approval and the signed `audited` events are the machinery `antstreet fund` has.

The checks are written from the request and the base's public surface alone (paths, names and
signatures, no bodies), so they cannot be fitted to a change. This module also holds what `plan`
and `check` share: the seal, the surface, and how a check's result on a tree is read.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re
import sys
import tempfile
import uuid
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from antstreet import gitrepo, held_out
from antstreet.approval import content_hashes, review_term_sheet
from antstreet.boss import DEFAULT_MODEL, BossError, InvalidDraftError, draft_term_sheet
from antstreet.budget import RESERVE_MICROS
from antstreet.gate import (
    Check,
    CheckResult,
    CheckStatus,
    missing_modules,
    run_gate,
    sandbox_available,
    secret_paths,
)
from antstreet.ledger import EventType
from antstreet.pipeline import Pipeline, Setup
from antstreet.redact import safe_text
from antstreet.rundir import Recorder, RunPaths
from antstreet.stream import Usage
from antstreet.termsheet import Task, TermSheet
from antstreet.worker import CLI, billing_mode

HOME_VAR = "BOSS_AUDIT_HOME"
STORE_DIR = ".boss-audit"
AUDIT_PROMPT = "audit_checks_v1.md"
PURPOSE = "audit_checks"  # the `purpose` of the boss_call event
# kn: a placeholder: the audit funds no worker, but the term sheet and the examiner's budget gate
# need a round with money in it; the sheet says so under the figure.
SHEET_BUDGET_MICROS = 1_000_000
PYTHONPATH = ("ws", "ws/src")  # a flat layout and a src layout
MAX_REQUEST_BYTES = 64 * 1024
MAX_SURFACE_CHARS = 30_000
MAX_SURFACE_FILES = 300
MAX_PARSE_BYTES = 256 * 1024
VENV = ".venv"  # where `uv sync` and `python -m venv .venv` put a repo's environment
_SKIPPED_DIRS = frozenset({"__pycache__", "node_modules", ".venv", "venv", "build", "dist"})
_SEAL = re.compile(r"audit seal: base=([0-9a-f]{40}|[0-9a-f]{64}) request_sha256=([0-9a-f]{64})\Z")


class AuditError(Exception):
    """An audit command refused or failed. The message says why and what to try."""


class CheckState(StrEnum):
    FAILING = "failing"
    PASSING = "passing"
    BLOCKED = "blocked"  # needs a module this environment has not got
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class Observed:
    state: CheckState
    detail: str


@dataclass(frozen=True, slots=True)
class Seal:
    base: str  # the commit the checks were written against
    request_sha256: str


@dataclass(frozen=True, slots=True)
class RepoEnv:
    site_packages: Path | None  # resolved; None: checks see the standard library and pytest only
    note: str  # one line for the screen: which packages the checks see, or why not the repo's


@dataclass(frozen=True, slots=True)
class PlanResult:
    run_id: str
    seal: str
    counted: int  # checks failing at the base: the ones a verdict can rest on
    total: int


def store_root(environ: Mapping[str, str]) -> Path:
    """`$BOSS_AUDIT_HOME` if set, else `~/.boss-audit` (of `$HOME` in `environ`)."""
    override = environ.get(HOME_VAR)
    if override:
        return Path(override).expanduser().resolve()
    home = environ.get("HOME")
    return (Path(home) if home else Path.home()).resolve() / STORE_DIR


def run_paths(store: Path, run_id: str) -> RunPaths:
    return RunPaths(Path(store) / ".boss" / "runs" / run_id)


def runs_in(store: Path) -> list[str]:
    runs = Path(store) / ".boss" / "runs"
    return sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []


def seal_brief(base: str, request_sha256: str) -> str:
    """The synthetic task's brief: machine-readable, and inside the term-sheet hash the investor's
    signed approval covers, so editing the base commit or the request voids the approval."""
    return f"audit seal: base={base} request_sha256={request_sha256}"


def request_hash(request: str) -> str:
    return hashlib.sha256(request.encode()).hexdigest()


def parse_seal(sheet: TermSheet) -> Seal:
    match = _SEAL.fullmatch(sheet.tasks[0].brief) if len(sheet.tasks) == 1 else None
    if match is None:
        raise AuditError(
            "this run's term sheet is not an audit seal: `antstreet audit plan` made none"
        )
    seal = Seal(match.group(1), match.group(2))
    if request_hash(sheet.idea) != seal.request_sha256:
        raise AuditError("the request in the term sheet is not the one the seal records")
    return seal


def seal_hash(sheet: TermSheet, checks_dir: Path, held_out_dir: Path) -> str:
    """One hash over what the investor approved: the term sheet (so the base and the request), every
    check file, every held-out file. Printed by `plan` and recorded on every verdict."""
    body = {
        "hashes": content_hashes(sheet, checks_dir),
        "held_out_hashes": held_out.hashes(held_out_dir),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


# --- the public surface -----------------------------------------------------------------------


def public_surface(tree: Path) -> str:
    """The paths in `tree` and, for each Python file outside tests, the public names and
    signatures: never a body, a docstring or a test. Bounded: a huge or hostile tree is cut."""
    lines: list[str] = []
    paths = sorted(p for p in tree.rglob("*") if p.is_file() and not p.is_symlink())
    shown = 0
    for path in paths:
        relative = path.relative_to(tree)
        if _SKIPPED_DIRS & set(relative.parts):
            continue
        shown += 1
        if shown > MAX_SURFACE_FILES:
            lines.append(f"... {len(paths) - MAX_SURFACE_FILES} more files")
            break
        lines.append(_one_line(relative.as_posix()))
        if path.suffix == ".py" and not _is_test_path(relative):
            lines += _signatures(path)
    text = "\n".join(lines)
    return text if len(text) <= MAX_SURFACE_CHARS else text[:MAX_SURFACE_CHARS] + "\n... cut"


def _is_test_path(relative: Path) -> bool:
    name = relative.name
    return (
        "tests" in relative.parts
        or "test" in relative.parts
        or name.startswith(("test_", "conftest"))
        or name.endswith("_test.py")
    )


def _one_line(text: str) -> str:
    """One line a person can read: controls shown, secrets masked, its leading spaces kept."""
    indent = " " * min(len(text) - len(text.lstrip(" ")), 8)
    return indent + safe_text(" ".join(text.split()), limit=200)


def _signatures(path: Path) -> list[str]:
    try:
        with path.open("rb") as fh:
            tree = ast.parse(fh.read(MAX_PARSE_BYTES).decode("utf-8-sig"))
    except (OSError, SyntaxError, ValueError, RecursionError):
        return []
    found: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            found.append(_one_line(f"  class {node.name}({bases})"))
            found += [
                _one_line(f"    {_def(m)}")
                for m in node.body
                if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
                and not m.name.startswith("_")
            ]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith(
            "_"
        ):
            found.append(_one_line(f"  {_def(node)}"))
    return found


def _def(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"{kind} {node.name}({ast.unparse(node.args)}){returns}"


# --- the repo's own environment ----------------------------------------------------------------


def repo_env(repo: Path, store: Path) -> RepoEnv:
    """The site-packages of `repo`'s own `.venv`, for the checks to import from. Found, never made:
    nothing is installed. It is the repo's code (an agent that worked there could have written it),
    so it is used only when an OS sandbox will run the checks, only if it is inside the repo and
    away from every secret, and only as an import path: the gate never runs its interpreter, its
    `.pth` files or its `sitecustomize`. It must be for the Python that runs the checks, or a
    compiled module would fail to load and be read as a failing check."""
    root = Path(repo).resolve()
    tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
    fix = (
        f"run `uv sync` (or `python3 -m venv .venv` and install the project into it) in {root} "
        f"with Python {tag.removeprefix('python')}, then run this again"
    )
    venv = root / VENV
    if not (venv / "pyvenv.cfg").is_file():
        return RepoEnv(
            None,
            f"{root} has no {VENV}, so the checks see the standard library and pytest only, and "
            f"a check that imports a third-party module is blocked. To give them the repo's "
            f"dependencies, {fix}",
        )
    site = venv / "lib" / tag / "site-packages"
    if not site.is_dir():
        found = sorted(p.parent.name for p in (venv / "lib").glob("python*/site-packages"))
        return RepoEnv(
            None,
            f"the repo's {VENV} is for {', '.join(found) or 'no Python this can read'}, not the "
            f"{tag} that runs the checks, so it is not used and a check that imports a "
            f"third-party module is blocked. To use it, {fix}",
        )
    real = site.resolve()
    secrets_near = (*secret_paths(real), Path(store).resolve())
    if not real.is_relative_to(root) or any(
        real.is_relative_to(s) or s.is_relative_to(real) for s in secrets_near
    ):
        return RepoEnv(
            None,
            f"the repo's {VENV} site-packages resolves to {real}, outside the repo or next to the "
            "audit store, so it is not used and a check that imports a third-party module is "
            f"blocked. Recreate it: {fix}",
        )
    if not sandbox_available():
        return RepoEnv(
            None,
            f"the repo's {VENV} is not used: its packages are the repo's code and run only inside "
            "an OS sandbox, which this machine has not got (`antstreet doctor` says why), so a "
            "check "
            "that imports a third-party module is blocked",
        )
    return RepoEnv(
        real,
        f"the repo's own {VENV} ({tag}), read-only inside the sandbox; nothing was installed",
    )


# --- reading a check's result -----------------------------------------------------------------


def tree_modules(tree: Path) -> frozenset[str]:
    """The top-level module names a tree defines, in its root or in `src/`."""
    names: set[str] = set()
    for root in (tree, tree / "src"):
        if root.is_dir():
            names |= {p.stem for p in root.glob("*.py")} | {p.name for p in root.iterdir()
                                                           if p.is_dir()}  # fmt: skip
    return frozenset(names)


def run_checks(
    tree: Path,
    paths: RunPaths,
    sheet: TermSheet,
    known: frozenset[str],
    only: Collection[str] | None = None,
    site_packages: Path | None = None,
) -> dict[str, Observed]:
    """Every sealed check (the visible ones, then any held-out), or just those in `only`, against
    a copy of `tree`.

    A check that fails because a module is missing is `BLOCKED`, not failing, when the module is
    not the standard library, not defined by either tree (`known`) and not named in the request:
    the environment lacks it, which says nothing about the change. A module the request names that
    nobody wrote is a real failure.
    """

    def wanted(checks: list[Check]) -> list[Check]:
        return [c for c in checks if only is None or c.id in only]

    results: list[CheckResult] = run_gate(
        tree, paths.checks, wanted(sheet.gate_checks()), pythonpath=PYTHONPATH,
        site_packages=site_packages,
    )  # fmt: skip
    held = wanted([h.to_check() for h in held_out.load(paths.held_out)])
    if held:
        results += run_gate(
            tree, paths.held_out, held, pythonpath=PYTHONPATH, site_packages=site_packages
        )
    return {r.check_id: observe(r, known, sheet.idea) for r in results}


def observe(result: CheckResult, known: frozenset[str], request: str) -> Observed:
    if result.status is CheckStatus.TIMEOUT:
        return Observed(CheckState.TIMEOUT, result.detail)
    if result.passed:
        return Observed(CheckState.PASSING, result.detail)
    needed = [
        m
        for m in missing_modules(result.output_tail)
        if m not in sys.stdlib_module_names
        and m not in known
        and not re.search(rf"\b{re.escape(m)}\b", request, re.IGNORECASE)
    ]
    if needed:
        return Observed(CheckState.BLOCKED, f"needs module {needed[0]!r}")
    return Observed(CheckState.FAILING, result.detail)


# --- plan -------------------------------------------------------------------------------------


def plan(
    repo: Path,
    request_file: Path,
    base_ref: str,
    *,
    store: Path,
    held_out_n: int,
    env: Mapping[str, str],
    executable: str = CLI,
    boss_model: str = DEFAULT_MODEL,
    boss_thinking: int | None = None,
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> PlanResult | None:
    """Seal checks for the request at `base_ref`. None when the investor rejected them; AuditError
    when nothing could be sealed. Reads the repository, never writes to it."""
    repo = Path(repo).resolve()
    store = Path(store)
    if store.resolve().is_relative_to(repo):
        raise AuditError(
            f"the audit store {store} is inside the repo {repo}; the checks must live outside it "
            f"(set {HOME_VAR})"
        )
    try:
        if not gitrepo.is_clean(repo):
            raise AuditError(
                f"the working tree of {repo} is not clean; commit or stash, then plan again"
            )
        base = gitrepo.resolve(repo, base_ref)
    except gitrepo.GitError as exc:
        raise AuditError(str(exc)) from exc
    request = _read_request(request_file)
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    paths = run_paths(store, run_id)
    _private_dirs(store)
    paths.root.mkdir(parents=True)
    say(f"Audit run {run_id}: asking the boss for checks against {base[:12]}...")
    with paths.writer() as ledger, tempfile.TemporaryDirectory(prefix="boss_audit_") as tmp:
        record = Recorder(ledger, run_id, round=0)
        base_tree = Path(tmp) / "base"
        try:
            gitrepo.export(repo, base, base_tree)
        except gitrepo.GitError as exc:
            record("boss", EventType.STOPPED, data={"reason": str(exc)})
            raise AuditError(str(exc)) from exc
        try:
            draft = draft_term_sheet(
                request,
                SHEET_BUDGET_MICROS,
                paths.checks,
                env=env,
                model=boss_model,
                executable=executable,
                thinking_tokens=boss_thinking,
                prompt_name=AUDIT_PROMPT,
                context=public_surface(base_tree),
            )
        except BossError as exc:
            _book(record, env, boss_model, boss_thinking, exc.usage, str(exc.outcome))
            record("boss", EventType.STOPPED, data={"reason": str(exc)})
            problems = exc.problems if isinstance(exc, InvalidDraftError) else []
            raise AuditError(
                "the boss could not produce usable checks: " + "; ".join([str(exc), *problems][:6])
            ) from exc
        _book(record, env, boss_model, boss_thinking, draft.usage, "completed")
        task = draft.sheet.tasks[0]
        brief = seal_brief(base, request_hash(request))
        sheet = dataclasses.replace(draft.sheet, tasks=(Task(task.id, brief, (".",)),))
        pipe = Pipeline(
            Setup((), boss_model, boss_thinking), repo, paths, ledger, run_id, env, executable,
            ask, say,
        )  # fmt: skip
        held = held_out_n > 0 and pipe.examine(sheet, held_out_n, RESERVE_MICROS)
        env_found = repo_env(repo, store)
        say(f"Environment: {env_found.note}.")
        say("Running the checks on the base...")
        observed = run_checks(
            base_tree, paths, sheet, tree_modules(base_tree),
            site_packages=env_found.site_packages,
        )  # fmt: skip
        approved = review_term_sheet(
            sheet, paths.checks, paths.root, ledger, run_id, ask=ask, say=say,
            notes=[_notes(sheet, paths, observed)],
            held_out_dir=paths.held_out if held else None,
        )  # fmt: skip
    if approved is None:
        return None
    counted = sum(o.state is CheckState.FAILING for o in observed.values())
    return PlanResult(
        run_id,
        seal_hash(approved, paths.checks, paths.held_out),
        counted,
        len(observed),
    )


def _read_request(path: Path) -> str:
    try:
        with Path(path).open("rb") as fh:
            raw = fh.read(MAX_REQUEST_BYTES + 1)
        text = raw.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise AuditError(f"cannot read the request {path}: {exc}") from exc
    if not text or text.startswith("-") or len(raw) > MAX_REQUEST_BYTES:
        raise AuditError(
            f"the request {path} must be 1 to {MAX_REQUEST_BYTES} bytes of text that does not "
            "start with '-'"
        )
    return text


def _private_dirs(store: Path) -> None:
    """The folders this command makes are the owner's alone; one that exists is left as it is."""
    for folder in (store, store / ".boss", store / ".boss" / "runs"):
        folder.mkdir(mode=0o700, exist_ok=True)


def _book(
    record: Recorder,
    env: Mapping[str, str],
    model: str,
    thinking: int | None,
    usage: Usage,
    out: str,
) -> None:
    record(
        "boss",
        EventType.BOSS_CALL,
        cost_micros=usage.cost_micros,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        tokens_cached=usage.tokens_cached,
        billing=billing_mode(env),
        data={"purpose": PURPOSE, "model": model, "thinking_tokens": thinking, "outcome": out},
    )


def _notes(sheet: TermSheet, paths: RunPaths, observed: Mapping[str, Observed]) -> str:
    """What each check does on the base, shown under the sheet. Failing there is the point: those
    are the ones a verdict rests on."""
    meaning = {
        CheckState.FAILING: "fails on the base: counted",
        CheckState.PASSING: "passes on the base: shown, not counted",
        CheckState.BLOCKED: "cannot run here: not counted",
        CheckState.TIMEOUT: "timed out on the base: not counted",
    }
    lines = ["Each check on the base commit (the audit funds no worker; the budget above is a "
             "placeholder):"]  # fmt: skip
    for check_id, seen in observed.items():
        extra = (
            f" ({seen.detail})" if seen.state in (CheckState.BLOCKED, CheckState.TIMEOUT) else ""
        )
        lines.append(f"  {check_id}: {meaning[seen.state]}{extra}")
    counted = sum(s.state is CheckState.FAILING for s in observed.values())
    lines.append(f"{counted} of {len(observed)} checks will be counted.")
    if counted == 0:
        lines.append("No check fails on the base, so every verdict would be inconclusive. Reject.")
    return "\n".join(lines)
