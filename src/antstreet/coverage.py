"""`antstreet fund --coverage`: the checks must cover every rule of the idea, and must catch a fake
product, before any worker is paid.

Most failed runs failed on a rule the idea states and no check tests (bench/results/
2026-10-02-why-the-firm-loses, section 2). This measures two gaps of a draft, in code, with no
model call:

- rule gaps (`antstreet.spec`): a scored rule no check cites (uncovered, or waived by the boss),
  and a rule whose citing checks lack what it names (anchor missing);
- weak checks: a check that passes on a stub product. There is no product yet, so mutation
  strength cannot run; the stand-in is three wrong products written by code from the task's file
  paths, where every name the checks import is a function that returns None, returns its first
  argument unchanged, or raises NotImplementedError. "Fails on an empty workspace" only proves a
  check imports something; a check a stub passes cannot tell that wrong product from a right one.

The boss is asked to redraft with the gaps named (at most MAX_REDRAFTS calls, each booked), and a
redraft is kept only when it has fewer gaps. What is left is shown above the term sheet: approving
that text is the investor's explicit waiver of every rule no check cites.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from antstreet import spec
from antstreet.gate import CheckStatus, GateError, run_gate
from antstreet.redact import safe_text
from antstreet.termsheet import TermSheet

FILE = "coverage.json"  # in the run's folder, beside rules.json; never in a worker's
PURPOSE = "coverage_redraft"  # the `purpose` of a redraft's boss_call event
MAX_REDRAFTS = 2
STUB_TIMEOUT_S = 30.0
# What every imported name does in each stub product. Code, never a model's.
STUBS = {
    "returns_none": "return None",
    "returns_input": "return args[0] if args else None",
    "raises": "raise NotImplementedError",
}
_STUB_MODULE = (
    "def _stub(*args, **kwargs):\n    {body}\n\n\n"
    "def __getattr__(name):  # PEP 562: `from m import f` and `m.f` both land here\n"
    "    if name.startswith('__'):\n        raise AttributeError(name)\n    return _stub\n"
)


@dataclass(frozen=True, slots=True)
class Gaps:
    unclaimed: tuple[str, ...]  # scored rules no check cites: uncovered, or waived by the boss
    anchor_missing: tuple[str, ...]
    weak: Mapping[str, tuple[str, ...]]  # check id -> the stubs it passed on
    unmeasured: str | None = None  # why the stubs could not be run, if they could not
    sha256: Mapping[str, str] = field(default_factory=dict)  # check id -> its file, as measured

    @property
    def size(self) -> int:
        return len(self.unclaimed) + len(self.anchor_missing) + len(self.weak)


def stub_modules(sheet: TermSheet) -> list[str]:
    """The task paths a stub is written to: the Python files inside the workspace."""
    found = []
    for task in sheet.tasks:
        for path in task.paths:
            pure = PurePosixPath(path)
            if path.endswith(".py") and not pure.is_absolute() and ".." not in pure.parts:
                found.append(path)
    return found


def weak_checks(
    sheet: TermSheet, checks_dir: Path
) -> tuple[dict[str, tuple[str, ...]], str | None]:
    """Each check that passes on some stub product, with the stubs it passed on; and why nothing
    was measured, or None. One gate run per stub."""
    modules = stub_modules(sheet)
    if not modules:
        return {}, "no task names a Python file to stub"
    passed: dict[str, list[str]] = {}
    for name, body in STUBS.items():
        with tempfile.TemporaryDirectory(prefix="boss_stub_ws_") as ws:
            for module in modules:
                target = Path(ws, module)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(_STUB_MODULE.format(body=body), encoding="utf-8")
            try:
                results = run_gate(Path(ws), checks_dir, sheet.gate_checks(), STUB_TIMEOUT_S)
            except GateError as exc:
                return {}, f"the gate could not run: {exc}"
        for r in results:
            if r.status is CheckStatus.PASSED:
                passed.setdefault(r.check_id, []).append(name)
    return {k: tuple(v) for k, v in passed.items()}, None


def measure(
    rules: spec.Split, sheet: TermSheet, checks_dir: Path, untested: Mapping[str, str]
) -> Gaps:
    """The gaps of a draft whose check files are in `checks_dir`."""
    sources = {c.id: (checks_dir / c.file).read_text(encoding="utf-8") for c in sheet.checks}
    claims = {c.id: c.criteria for c in sheet.checks}
    report = spec.verify(rules, claims, sources, untested)
    weak, unmeasured = weak_checks(sheet, checks_dir)
    return Gaps(
        unclaimed=_rules_in(report, "uncovered", "waived"),
        anchor_missing=_rules_in(report, "anchor_missing"),
        weak=weak,
        unmeasured=unmeasured,
        sha256={c: _sha(sources[c]) for c in weak},
    )


def _rules_in(report: spec.SpecReport, *states: str) -> tuple[str, ...]:
    return tuple(s.rule for s in report.statuses if s.state in states)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def feedback(gaps: Gaps, sheet: TermSheet) -> str:
    """What the boss is told to fix in its redraft. Code's text: rule ids, rule ids of the weak
    checks and stub names, never anything a model wrote."""
    lines = []
    if gaps.unclaimed:
        lines.append(
            f"- No check cites {', '.join(gaps.unclaimed)}. Write a check for each. List a rule in "
            "`untested` only if no pytest file can observe it."
        )
    if gaps.anchor_missing:
        lines.append(
            f"- The checks citing {', '.join(gaps.anchor_missing)} lack what the rule names (its "
            "exception, type, size or non-ASCII string). Assert it."
        )
    cited = {c.id: c.criteria for c in sheet.checks}
    for check, stubs in sorted(gaps.weak.items()):
        about = ", ".join(cited.get(check, ())) or "no rule"
        lines.append(
            f"- A check citing {about} passed against a fake product in which every function "
            f"{' / '.join(_STUB_WORDS[s] for s in stubs)}. Assert results only a correct product "
            "gives."
        )
    return (
        "Code measured your previous draft of these checks. Write the whole draft again, fixing:\n"
        + "\n".join(lines)
    )


_STUB_WORDS = {
    "returns_none": "returns None",
    "returns_input": "returns its first argument unchanged",
    "raises": "raises NotImplementedError",
}


def save(path: Path, gaps: Gaps, redrafts: int) -> None:
    data = {
        "redrafts": redrafts,
        "weak": {c: {"stubs": list(s), "sha256": gaps.sha256[c]} for c, s in gaps.weak.items()},
        "unmeasured": gaps.unmeasured,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def gate_view(
    path: Path, report: spec.SpecReport, sheet: TermSheet, checks_dir: Path
) -> tuple[str, dict[str, Any]]:
    """The gate's lines above the term sheet, and what the approval records. The waived rules are
    recomputed from the files now; a weak flag counts only for a check unchanged since it was
    measured (an edited check is said to be unmeasured)."""
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise spec.SpecError(
            f"{FILE} cannot be read ({exc}), and this run was started with --coverage, so its "
            "gate cannot be shown; start again with `antstreet fund --coverage`"
        ) from exc
    recorded = saved.get("weak")
    recorded = recorded if isinstance(recorded, dict) else {}
    weak: dict[str, list[str]] = {}
    changed = []
    for check in sheet.checks:
        entry = recorded.get(check.id)
        if not isinstance(entry, dict):
            continue
        try:
            now = _sha((checks_dir / check.file).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            now = None
        stubs = entry.get("stubs")
        if now == entry.get("sha256") and isinstance(stubs, list):
            weak[check.id] = [s for s in stubs if s in STUBS]
        else:
            changed.append(check.id)
    waived = list(_rules_in(report, "uncovered", "waived"))
    redrafts = saved.get("redrafts")
    redrafts = redrafts if type(redrafts) is int else "?"
    lines = [f"COVERAGE GATE (--coverage)  boss redrafts {redrafts} of {MAX_REDRAFTS}"]
    if waived:
        lines.append(
            f"  APPROVING THIS SHEET IS YOUR WAIVER of {', '.join(waived)}: no check tests them."
        )
    else:
        lines.append("  Every rule is cited by a check.")
    if saved.get("unmeasured"):
        lines.append(f"  Stub products not run: {safe_text(str(saved['unmeasured']), limit=200)}.")
    for check_id, passed in weak.items():
        words = " / ".join(_STUB_WORDS[s] for s in passed)
        lines.append(f"  WEAK {check_id}: passes on a fake product where every function {words}.")
    if changed:
        lines.append(f"  Edited since the stub run, not measured: {', '.join(changed)}.")
    return "\n".join(lines), {"investor_waived": waived, "weak": weak}
