"""One benchmark cell's result: a task run once through one arm, scored by the hidden checks."""

from __future__ import annotations

import json
from dataclasses import MISSING, asdict, dataclass, fields
from pathlib import Path

from antstreet.errors import INFRASTRUCTURE

ARMS = ("single", "firm", "single-review")
RESULT_FILE = "result.json"
# Set by the runner when it can tell; everything else is labelled by hand with evidence kept.
FAILURE_CLASSES = ("product", "model", "grading", "infrastructure", "unlabelled")
# Outcomes where the environment cut the run off (usage limit, login, isolation), not the product;
# the runner prefixes them with `boss:` when the boss's own call hit them.
INFRA_OUTCOMES = frozenset(str(o) for o in INFRASTRUCTURE) | {"isolation"}
_NONE = type(None)
# JSON types of a result file, checked on load; bool is refused everywhere (it is an int in Python).
_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "task": str,
    "arm": str,
    "rep": int,
    "set_hash": str,
    "model": str,
    "budget_micros": int,
    "hidden": dict,
    "visible_passed": (int, _NONE),
    "visible_total": (int, _NONE),
    "cost_micros": int,
    "boss_micros": int,
    "unknown_cost_events": int,
    "outcome": str,
    "failure_class": (str, _NONE),
    "duration_s": (int, float),
    "firm_args": str,
    "wrong_checks": (int, _NONE),
    "held_out_passed": (int, _NONE),
    "held_out_total": (int, _NONE),
    "held_out_wrong": (int, _NONE),
    "final_status": (str, _NONE),
}


@dataclass(frozen=True, slots=True)
class CellResult:
    task: str
    arm: str  # one of ARMS
    rep: int
    set_hash: str  # which task set this ran against
    model: str
    budget_micros: int
    hidden: dict[str, str]  # hidden check id -> "passed" | "failed" | "timeout"
    visible_passed: int | None  # the firm's own term-sheet checks; None for the single arm
    visible_total: int | None
    cost_micros: int  # estimated spend with known cost, boss calls included
    boss_micros: int  # part of cost_micros spent by the boss; 0 for the single arm
    unknown_cost_events: int
    outcome: str  # the worker's outcome, or why no worker ran
    failure_class: str | None  # None when every hidden check passed
    duration_s: float
    firm_args: str = ""  # extra `antstreet fund` options the firm arm ran with, e.g. "--rounds 3"
    # Firm only: boss-written checks that the task's reference solution fails. Such a check
    # demands something the idea does not; None when not measured (older results, single arm).
    wrong_checks: int | None = None
    # Firm only, and only when the run had held-out checks: how many of them the assembled product
    # passed, out of how many. A check the run did not get to grade counts as not passed. Compared
    # with `hidden`, they tell whether a held-out failure predicts a hidden-check failure. None
    # when the run had none (older results, the single arm, no `--held-out`).
    held_out_passed: int | None = None
    held_out_total: int | None = None
    # Firm only: held-out checks the task's reference solution fails. Such a check demands
    # something the idea does not, so a product failing it says nothing about the product; None when
    # not measured (older results, the single arm, no held-out checks on disk).
    held_out_wrong: int | None = None
    # Single arms only: the status word of the agent's last slice (`done`, `blocked`, ...), the
    # claim the KPI scorecard's false-pass rate tests. None when no slice ended with a report, and
    # in older results and firm cells; the firm's claim is its checks, not a word, so it has none.
    final_status: str | None = None

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}, got {self.arm!r}")
        if self.failure_class is not None and self.failure_class not in FAILURE_CLASSES:
            raise ValueError(f"unknown failure class {self.failure_class!r}")
        if self.passed and self.failure_class not in (None, "infrastructure"):
            raise ValueError("a passing cell cannot have a failure class")
        held = (self.held_out_passed, self.held_out_total)
        if (held[0] is None) != (held[1] is None):
            raise ValueError(
                "held_out_passed and held_out_total are recorded together or not at all"
            )
        if held[0] is not None and held[1] is not None and not 0 <= held[0] <= held[1]:
            raise ValueError(
                f"held_out_passed {held[0]} must be between 0 and held_out_total {held[1]}"
            )

    @property
    def hidden_passed(self) -> int:
        return sum(status == "passed" for status in self.hidden.values())

    @property
    def hidden_total(self) -> int:
        return len(self.hidden)

    @property
    def passed(self) -> bool:
        """A cell passes only when every hidden check passed."""
        return self.hidden_total > 0 and self.hidden_passed == self.hidden_total

    @property
    def counted(self) -> bool:
        """False for a cell the environment cut off, whatever its product scored (B71). Derived
        from `outcome`, not only the stored class: old results of a passing cut-off cell carry
        `failure_class: null`."""
        return (
            self.failure_class != "infrastructure"
            and self.outcome.removeprefix("boss:") not in INFRA_OUTCOMES
        )

    def save(self, cell_dir: Path) -> None:
        cell_dir.mkdir(parents=True, exist_ok=True)
        (cell_dir / RESULT_FILE).write_text(json.dumps(asdict(self), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> CellResult:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError name no file
            raise ValueError(f"{path}: not valid JSON: {exc}") from exc
        known = {f.name for f in fields(cls)}
        required = {f.name for f in fields(cls) if f.default is MISSING}
        if not isinstance(raw, dict) or not required <= set(raw) <= known:
            raise ValueError(f"{path}: fields differ from the result schema")
        for name, kinds in _FIELD_TYPES.items():
            if name in raw and (isinstance(raw[name], bool) or not isinstance(raw[name], kinds)):
                raise ValueError(f"{path}: field {name!r} has the wrong type: {raw[name]!r}")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in raw["hidden"].items()):
            raise ValueError(f"{path}: field 'hidden' must map check ids to status strings")
        try:
            return cls(**raw)
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc


def cell_dir(results_dir: Path, task: str, arm: str, rep: int) -> Path:
    return results_dir / task / arm / f"rep{rep}"


def load_results(results_dir: Path) -> list[CellResult]:
    """Every result under a results folder, in a stable order."""
    paths = sorted(results_dir.glob(f"*/*/rep*/{RESULT_FILE}"))
    return [CellResult.load(p) for p in paths]
