"""`antstreet audit check`: run sealed checks against a head commit and write the gate's signed
verdict.

Nothing here trusts the audited repository or the agent that worked in it. The ledger, the approval
signature and the check files are verified first; `head` must descend from the sealed base; both
trees are exported from git objects only (`gitrepo.export`); the checks run in the gate on a copy of
each. A counted check is one that fails on the base (read live, so no stored status can be edited):
the verdict is refuted when a counted check fails on the head of a change claimed done.
"""

from __future__ import annotations

import ast
import hashlib
import re
import tempfile
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from antstreet import gitrepo, held_out, mutate
from antstreet.approval import NotApprovedError, require_approval
from antstreet.audit import (
    _SKIPPED_DIRS,
    MAX_PARSE_BYTES,
    PYTHONPATH,
    AuditError,
    CheckState,
    _is_test_path,
    parse_seal,
    repo_env,
    run_checks,
    run_paths,
    runs_in,
    seal_hash,
    tree_modules,
)
from antstreet.gate import DEFAULT_TIMEOUT_S, CheckStatus, run_tree, sandbox_available
from antstreet.ledger import AUDIT_ACTOR, EventType
from antstreet.redact import safe_text
from antstreet.rundir import Recorder, RunPaths
from antstreet.sandbox import SandboxMode
from antstreet.termsheet import TermSheet

CLAIMS = ("done", "none")
MODES = ("pre_registered", "post_hoc")
VERDICTS = ("refuted", "unrefuted", "inconclusive", "no_claim")
MAX_LISTED = 50  # a list kept in the ledger event is cut here
MAX_CLAIM_TEXT_BYTES = 64 * 1024
# kn: leak thresholds (4+ word test names, 16+ character literals) are a guess; tune them on real
# audited diffs
MIN_NAME_PARTS = 4  # test_<three or more words>: a shorter name is common enough to collide
MIN_LITERAL_CHARS = 16
STRENGTH_TIMEOUT_S = 300.0  # all mutants together; one is never cut short to fit
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_AGENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:@/+-]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class Strength:
    """How much each counted check that passes on the head bites: of `mutants` mutants of the
    lines the change touched, how many it fails on. Advisory: it never changes the verdict."""

    mutants: int  # each one run against every measured check
    found: int  # mutants the change offered, before the cap
    killed: Mapping[str, int]  # check id -> mutants it failed (or timed out) on
    note: str  # why fewer than `found`, or none, were run; empty otherwise

    def weak(self) -> list[str]:
        """Checks that killed no mutant: each would pass every broken version tried."""
        return [i for i, k in self.killed.items() if k == 0] if self.mutants else []

    def to_data(self) -> dict[str, object]:
        return {
            "mutants": self.mutants,
            "found": self.found,
            "killed": dict(list(self.killed.items())[:MAX_LISTED]),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class Verdict:
    """What one `antstreet audit check` found. `to_data` is the `audited` event's `data`."""

    run: str
    base: str
    head: str
    seal: str
    verdict: str
    claim: str
    claim_mode: str
    counted: int
    failed: tuple[str, ...]
    blocked: tuple[str, ...]  # counted checks that could not be run on the head
    leaks: tuple[str, ...]
    tests_deleted: tuple[str, ...]
    regressions: tuple[str, ...]
    agent: str | None
    claim_text_sha256: str | None
    described: Mapping[str, str]  # check id -> its description, for the screen only
    environment: str = ""  # which packages the checks saw (`audit.repo_env`), for the screen only
    strength: Strength | None = None  # None: not measured (`--no-strength`)

    def to_data(self) -> dict[str, object]:
        return {
            "base": self.base,
            "head": self.head,
            "seal": self.seal,
            "verdict": self.verdict,
            "claim": self.claim,
            "claim_mode": self.claim_mode,
            "counted": self.counted,
            "failed": list(self.failed[:MAX_LISTED]),
            "blocked": list(self.blocked[:MAX_LISTED]),
            "leaks": list(self.leaks[:MAX_LISTED]),
            "tests_deleted": list(self.tests_deleted[:MAX_LISTED]),
            "regressions": list(self.regressions[:MAX_LISTED]),
            "agent": self.agent,
            "claim_text_sha256": self.claim_text_sha256,
            "strength": self.strength.to_data() if self.strength else None,
        }


def agent_label(text: str) -> str:
    if not _AGENT.fullmatch(text):
        raise ValueError(f"{text!r} is not a label of 1 to 64 letters, digits and . _ : @ / + -")
    return text


def decide(
    claim: str,
    counted: int,
    failed: Collection[str],
    blocked: Collection[str],
    leaks: Collection[str],
) -> str:
    """The verdict. Only a claim of `done` can be refuted: the point is to catch a false 'done'.

    A sealed check that fails on the head refutes it. Otherwise the checks must have spoken for the
    verdict to mean anything: none that fail on the base (nothing discriminates), one that could not
    run on the head, or text of the sealed checks in the diff (the change may have been fitted to
    them) all leave it inconclusive. Passing every counted check is not proof, only no refutation.
    """
    if claim != "done":
        return "no_claim"
    if failed:
        return "refuted"
    if counted == 0 or blocked or leaks:
        return "inconclusive"
    return "unrefuted"


def claim_mode(commits: list[gitrepo.Commit], sealed_at: datetime) -> str:
    """`pre_registered` when there is at least one commit and every one is dated after the seal.
    The dates are the committer's own and can be forged: this is a record, not a proof."""
    if commits and all(c.committed_at > sealed_at for c in commits):
        return "pre_registered"
    return "post_hoc"


# --- the leak scan ----------------------------------------------------------------------------


def leak_scan(diff: str, check_texts: Mapping[str, str], request: str) -> list[str]:
    """Which sealed checks the added lines of `diff` quote: a test function named in them, or a
    string literal of theirs. Names and literals the request itself contains are not leaks: the
    agent was given them. A long name or literal is rare by chance and a short one is not, so only
    long ones count, and a hit only ever downgrades `unrefuted`."""
    added = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    asked = request.lower()
    found: set[str] = set()
    for check_id, text in check_texts.items():
        try:
            tree = ast.parse(text.lstrip("\ufeff"))
        except (SyntaxError, ValueError, RecursionError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = node.name
                parts = name.split("_")
                named = name.startswith(("test", "Test")) and len(parts) >= MIN_NAME_PARTS
                if named and name.lower() not in asked and re.search(rf"\b{name}\b", added):
                    found.add(f"{check_id} test name")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value.strip()
                if (
                    len(literal) >= MIN_LITERAL_CHARS
                    and literal.lower() not in asked
                    and literal in added
                ):
                    found.add(f"{check_id} string literal")
    return sorted(found)


# --- the base's own tests against the head's code ---------------------------------------------


def base_tests_on_head(
    base_tree: Path, head_tree: Path, site_packages: Path | None = None
) -> tuple[list[str], list[str]]:
    """(test files the head no longer has, base tests that pass on the base and fail on the head's
    code). The second runs the base's `tests/` folder over the head's code, so a test the agent
    deleted or weakened still speaks. Both empty when the base has no `tests/` or a run produced no
    report. Not part of the verdict: a request that changes behaviour breaks old tests honestly."""
    tests = base_tree / "tests"
    if not tests.is_dir():
        return [], []
    deleted = sorted(
        p.relative_to(base_tree).as_posix()
        for p in tests.rglob("test_*.py")
        if not (head_tree / p.relative_to(base_tree)).is_file()
    )
    before, after = (
        run_tree(tree, tests, "tests", pythonpath=PYTHONPATH, site_packages=site_packages)
        for tree in (base_tree, head_tree)
    )
    if not before.tests or not after.tests:
        return deleted, []
    passed = CheckStatus.PASSED
    broken = sorted(
        n for n, s in before.tests.items() if s is passed and after.tests.get(n) != passed
    )
    return deleted, broken


# --- check strength: the counted checks against mutants of the change ------------------------


def measure_strength(
    base_tree: Path,
    head_tree: Path,
    paths: RunPaths,
    sheet: TermSheet,
    known: frozenset[str],
    measured: list[str],
    *,
    site_packages: Path | None = None,
    cap: int = mutate.DEFAULT_CAP,
    timeout_s: float = STRENGTH_TIMEOUT_S,
) -> Strength:
    """Run the `measured` checks against mutants of the lines `head_tree` changed from
    `base_tree`, through the gate and only inside an OS sandbox: a mutant is the audited code,
    edited. A check kills a mutant when it fails or times out on it. Each mutant is written into
    `head_tree` for its run and the file put back after."""
    if not measured:
        return Strength(
            0, 0, {}, "no counted check passes on the head, so there is none to measure"
        )
    if not sandbox_available():
        return Strength(
            0, 0, {}, "mutants run only inside an OS sandbox, which this run has not got "
            "(`antstreet doctor` says why)",
        )  # fmt: skip
    found, total = mutate.mutants(_changed_sources(base_tree, head_tree), cap)
    notes: list[str] = []
    if total > len(found):
        notes.append(f"{total} mutants found; {len(found)} taken, spread evenly across them")
    killed = dict.fromkeys(measured, 0)
    run = 0
    deadline = time.monotonic() + timeout_s
    for mutant in found:
        if time.monotonic() >= deadline:
            notes.append(f"stopped at the {timeout_s:g}s limit after {run} of {len(found)}")
            break
        target = head_tree / mutant.path
        original = target.read_bytes()
        try:
            target.write_text(mutant.source, encoding="utf-8")
            seen = run_checks(
                head_tree, paths, sheet, known, only=measured, site_packages=site_packages,
                sandbox=SandboxMode.REQUIRE, timeout_s=min(DEFAULT_TIMEOUT_S, timeout_s),
            )  # fmt: skip
        finally:
            target.write_bytes(original)
        run += 1
        for check_id in measured:
            if seen[check_id].state in (CheckState.FAILING, CheckState.TIMEOUT):
                killed[check_id] += 1
    if not found:
        notes.append("the change has no line a mutant can be made of")
    return Strength(run, total, killed, "; ".join(notes))


def _changed_sources(base_tree: Path, head_tree: Path) -> dict[str, tuple[str, str]]:
    """path -> (base text, head text) for each Python file outside tests that the head added or
    changed. A symlink, a file too large or not UTF-8 is left out: it is never written to."""
    root = head_tree.resolve()
    files: dict[str, tuple[str, str]] = {}
    for path in sorted(head_tree.rglob("*.py")):
        relative = path.relative_to(head_tree)
        if (
            _SKIPPED_DIRS & set(relative.parts)
            or _is_test_path(relative)
            or path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(root)
        ):
            continue
        new = _source(path)
        old_path = base_tree / relative
        old = _source(old_path) if old_path.is_file() and not old_path.is_symlink() else ""
        if new is not None and new != old:
            files[relative.as_posix()] = (old or "", new)
    return files


def _source(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            raw = fh.read(MAX_PARSE_BYTES + 1)
        return raw.decode("utf-8") if len(raw) <= MAX_PARSE_BYTES else None
    except (OSError, UnicodeDecodeError):
        return None


# --- the command ------------------------------------------------------------------------------


def check(
    run_id: str,
    head_ref: str,
    *,
    repo: Path,
    store: Path,
    claim: str,
    claim_text: Path | None = None,
    agent: str | None = None,
    strength: bool = True,
    max_mutants: int = mutate.DEFAULT_CAP,
    strength_timeout_s: float = STRENGTH_TIMEOUT_S,
) -> Verdict:
    """Audit `head_ref` of `repo` against run `run_id` of `store`, record the verdict, return it.
    With `strength`, also measure how much each counted check bites (`measure_strength`); that is
    recorded beside the verdict and never changes it.

    Raises AuditError, NotApprovedError, a ledger error or a GitError when something it verifies
    does not hold; nothing is written to the ledger then.
    """
    if claim not in CLAIMS:
        raise AuditError(f"claim must be one of {', '.join(CLAIMS)}")
    paths = _find(store, run_id)
    if paths.investor_key is None or not paths.investor_key.is_file():
        raise AuditError(f"the audit store has no investor key at {paths.investor_key}")
    claim_hash = _hash_claim_text(claim_text)
    events = paths.events()  # chain, anchor and every signature, or a ledger error
    try:
        sheet = TermSheet.from_json((paths.root / "term_sheet.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"run {run_id} has no readable term sheet ({exc})") from exc
    if not sheet.approved_by_investor:
        raise NotApprovedError("the term sheet is not marked approved")
    require_approval(events, sheet, paths.checks, paths.held_out, paths.investor_key)
    seal = parse_seal(sheet)
    sealed_at = max(
        datetime.fromisoformat(e.ts)
        for e in events
        if e.event is EventType.APPROVED and e.actor == "investor"
    )
    try:
        repo = Path(repo).resolve()
        head = gitrepo.resolve(repo, head_ref)
        base = gitrepo.resolve(repo, seal.base)
        if not gitrepo.is_ancestor(repo, base, head):
            raise AuditError(
                f"{head[:12]} does not descend from the sealed base {base[:12]}: it is not a "
                "change to that code. Audit a commit on top of the base"
            )
        mode = claim_mode(gitrepo.commits_between(repo, base, head), sealed_at)
        diff = gitrepo.diff(repo, base, head)
        env_found = repo_env(repo, store)
        site = env_found.site_packages
        with tempfile.TemporaryDirectory(prefix="boss_audit_") as tmp:
            base_tree, head_tree = Path(tmp) / "base", Path(tmp) / "head"
            gitrepo.export(repo, base, base_tree)
            gitrepo.export(repo, head, head_tree)
            known = tree_modules(base_tree) | tree_modules(head_tree)
            # kn: the base is run again on every check; cache by seal hash if one run is audited
            # against many heads.
            on_base = run_checks(base_tree, paths, sheet, known, site_packages=site)
            counted = sorted(i for i, o in on_base.items() if o.state is CheckState.FAILING)
            on_head = run_checks(head_tree, paths, sheet, known, only=counted, site_packages=site)
            deleted, regressions = base_tests_on_head(base_tree, head_tree, site)
            bites = None
            if strength:
                measured = [i for i in counted if on_head[i].state is CheckState.PASSING]
                try:
                    bites = measure_strength(
                        base_tree, head_tree, paths, sheet, known, measured, site_packages=site,
                        cap=max_mutants, timeout_s=strength_timeout_s,
                    )  # fmt: skip
                except Exception as exc:  # advisory: a failure here must never cost the verdict
                    why = safe_text(f"{type(exc).__name__}: {exc}", limit=200)
                    bites = Strength(0, 0, {}, f"not measured: {why}")
    except gitrepo.GitError as exc:
        raise AuditError(str(exc)) from exc
    failed = [i for i in counted if on_head[i].state is CheckState.FAILING]
    blocked = [i for i in counted if on_head[i].state in (CheckState.BLOCKED, CheckState.TIMEOUT)]
    leaks = leak_scan(diff, _check_texts(sheet, paths), sheet.idea)
    result = Verdict(
        run=run_id,
        base=base,
        head=head,
        seal=seal_hash(sheet, paths.checks, paths.held_out),
        verdict=decide(claim, len(counted), failed, blocked, leaks),
        claim=claim,
        claim_mode=mode,
        counted=len(counted),
        failed=tuple(failed),
        blocked=tuple(blocked),
        leaks=tuple(leaks),
        tests_deleted=tuple(deleted),
        regressions=tuple(regressions),
        agent=agent,
        claim_text_sha256=claim_hash,
        described=_descriptions(sheet, paths, failed),
        environment=env_found.note,
        strength=bites,
    )
    with paths.writer() as ledger:
        Recorder(ledger, run_id, 0)(AUDIT_ACTOR, EventType.AUDITED, data=result.to_data())
    return result


def _find(store: Path, run_id: str) -> RunPaths:
    if not _RUN_ID.fullmatch(run_id) or run_id not in runs_in(store):
        raise AuditError(
            f"no audit run {run_id!r} under {store}; `antstreet audit report --all` lists them"
        )
    return run_paths(store, run_id)


def _hash_claim_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        with Path(path).open("rb") as fh:
            raw = fh.read(MAX_CLAIM_TEXT_BYTES + 1)
    except OSError as exc:
        raise AuditError(f"cannot read the claim text {path}: {exc}") from exc
    if len(raw) > MAX_CLAIM_TEXT_BYTES:
        raise AuditError(f"the claim text {path} is over {MAX_CLAIM_TEXT_BYTES} bytes")
    return hashlib.sha256(raw).hexdigest()


def _check_texts(sheet: TermSheet, paths: RunPaths) -> dict[str, str]:
    texts = {}
    for spec in sheet.checks:
        texts[spec.id] = (paths.checks / spec.file).read_text(encoding="utf-8", errors="replace")
    for held in held_out.load(paths.held_out):
        texts[held.id] = (paths.held_out / held.file).read_text(encoding="utf-8", errors="replace")
    return texts


def _descriptions(sheet: TermSheet, paths: RunPaths, ids: Collection[str]) -> dict[str, str]:
    described = {c.id: c.description for c in sheet.checks}
    described |= {h.id: h.source for h in held_out.load(paths.held_out)}
    return {i: " ".join(described.get(i, "").split())[:200] for i in ids}


def render_check(v: Verdict) -> str:
    """The screen text. Check ids and descriptions only: a failing check's code never leaves the
    store, so this output is safe to show an agent that is not the one being audited."""
    lines = [
        f"Run {v.run}: head {v.head[:12]} on base {v.base[:12]}",
        f"Verdict: {v.verdict.upper()} (claim: {v.claim}, {v.claim_mode.replace('_', '-')})",
        f"Counted checks (failing on the base): {v.counted}; failing on the head: {len(v.failed)}",
    ]
    lines += [f"  {i} failed: {v.described.get(i) or '(no description)'}" for i in v.failed]
    if v.environment:
        lines.append(f"Environment: {v.environment}.")
    if v.blocked:
        lines.append(f"Could not run on the head: {', '.join(v.blocked)}")
    if v.leaks:
        lines.append(
            "Text of the sealed checks appears in the change (" + "; ".join(v.leaks) + "): a pass "
            "is not trusted, so an otherwise passing audit is inconclusive."
        )
    if v.tests_deleted:
        lines.append(f"Test files of the base that the head does not have: {len(v.tests_deleted)}")
    if v.regressions:
        lines.append(
            f"Tests of the base that pass on the base and fail on the head's code: "
            f"{len(v.regressions)} (not part of the verdict; a changed behaviour breaks old tests)"
        )
    if v.claim_mode == "post_hoc":
        lines.append(
            "Post-hoc: some commit is dated before the seal, so the work may predate the checks. "
            "Commit dates are set by the committer and can be forged either way."
        )
    if v.strength is not None:
        lines += render_strength(v.strength)
    if v.verdict == "unrefuted":
        lines.append(
            "Unrefuted is not proof: the sealed checks catch only some wrong implementations."
        )
    return "\n".join(lines)


def render_strength(s: Strength) -> list[str]:
    lines = [
        f"Check strength (advisory, never part of the verdict): {s.mutants} "
        f"mutant{'' if s.mutants == 1 else 's'} of the lines "
        "the change touched, each run against the counted checks that pass on the head."
    ]
    if s.note:
        lines.append(f"  ({s.note})")
    if s.mutants:
        weak = s.weak()
        lines += [
            f"  {i} kills {k}/{s.mutants}"
            + (": WEAK, it would pass broken code" if i in weak else "")
            for i, k in s.killed.items()
        ]
        lines.append(
            "  A mutant that survives may change nothing a check can see, so a kill count is how "
            "much a check bites, not a catch rate."
        )
    return lines
