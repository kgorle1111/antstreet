"""The staged flow around the firm's loop: what runs before the term sheet is approved, while a
dispute is open, and after the workers finish.

Each step is a role the investor chose (`boss fund --roles`). A role drafts and never decides: what
it writes reaches the investor as a note, and only the investor's answer changes anything. Every
call is booked as a `role_call` event under the role's actor, at round 0 so that a round's budget
and the run's spend ceiling stay what the investor funded, whether the call worked or not. A
failed role is never read as "no findings": the investor is told in one line, the run goes on
without its output, and the one step that cannot (the staged draft) falls back to the boss.

With no roles chosen every method is a no-op, and the run is the run `boss fund` always was.
"""

from __future__ import annotations

import functools
import json
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.firm import Advise, FirmConfig, config_data
from boss.ledger import Event, EventType, LedgerWriter
from boss.redact import safe_text
from boss.roles import registry
from boss.roles.advisory import advise_on_dispute, audit_checks, render_advice, render_audit
from boss.roles.base import RoleError, RoleSpec, ledger_fields
from boss.roles.engineering import StagedDraftError, draft_staged, render_coverage, stories_text
from boss.roles.product import StoryReview, review_stories, uncovered_fragments, write_stories
from boss.roles.stories import Stories
from boss.rundir import Recorder, RunPaths
from boss.stream import Usage
from boss.termsheet import TermSheet

Ask = Callable[[str], str]
Say = Callable[[str], None]

# A role that cannot work without another's output, and why. `system_designer` alone would pay
# for a design that produces no checks.
NEEDS = {
    "user_agent": ("product_manager",),
    "tester": ("product_manager", "system_designer"),
    "system_designer": ("tester",),
}
_WHY = {
    "user_agent": "it reads the product manager's stories",
    "tester": "it writes checks for the stories and the design",
    "system_designer": "a design alone produces no checks",
}
_STORIES_CHARS = 20_000


class RolesError(ValueError):
    """The roles asked for cannot be run. The message says what to change."""


def parse_roles(text: str, known: Iterable[str]) -> tuple[str, ...]:
    """The role names in a `--roles a,b,c` list ("all" is every known role), sorted, or RolesError.
    Checked before anything is spent."""
    names_known = sorted(known)
    names = {n.strip() for n in text.split(",") if n.strip()}
    if unknown := sorted(names - {"all", *names_known}):
        shown = ", ".join(repr(n) for n in unknown)
        raise RolesError(f"Unknown role(s) {shown}. Known roles: {', '.join(names_known)}, or all.")
    if "all" in names:
        names = set(names_known)
    problems = [
        f"{role} needs {' and '.join(need)} ({_WHY[role]})."
        for role, need in NEEDS.items()
        if role in names and not names.issuperset(need)
    ]
    if problems:
        raise RolesError("\n".join(problems))
    return tuple(sorted(names))


@dataclass(frozen=True, slots=True)
class Setup:
    """The roles a run was started with. Recorded on the run's `started` event so that
    `boss resume` and the report know them; `FirmConfig` never carries role names."""

    roles: tuple[str, ...]
    model: str  # the model of every role call: the boss's
    thinking_tokens: int | None

    def data(self) -> dict[str, Any]:
        return {
            "names": list(self.roles),
            "model": self.model,
            "thinking_tokens": self.thinking_tokens,
        }


def recorded_setup(events: Sequence[Event]) -> Setup | None:
    for e in events:
        raw = e.data.get("roles") if e.event is EventType.STARTED else None
        if isinstance(raw, dict) and isinstance(raw.get("names"), list):
            thinking = raw.get("thinking_tokens")
            names = tuple(str(n) for n in raw["names"])
            return Setup(
                names, str(raw.get("model", "")), thinking if type(thinking) is int else None
            )
    return None


@dataclass(frozen=True, slots=True)
class Plan:
    sheet: TermSheet
    notes: tuple[str, ...]  # opinions shown under the sheet; they bind nothing


@functools.cache
def _spec(name: str) -> RoleSpec:
    return registry()[name]


@dataclass(frozen=True, slots=True)
class Pipeline:
    setup: Setup
    project: Path
    paths: RunPaths
    ledger: LedgerWriter
    run_id: str
    env: Mapping[str, str]
    executable: str
    ask: Ask
    say: Say

    def _on(self, name: str) -> bool:
        return name in self.setup.roles

    def _call_args(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "model": self.setup.model,
            "executable": self.executable,
            "thinking_tokens": self.setup.thinking_tokens,
        }

    def _book(self, spec: RoleSpec, usage: Usage, outcome: str, result: str, **data: Any) -> None:
        fields = ledger_fields(
            spec, usage, outcome, model=self.setup.model, env=self.env, result=result, **data
        )
        Recorder(self.ledger, self.run_id, 0)(spec.actor, EventType.ROLE_CALL, **fields)

    def _call[T](
        self,
        spec: RoleSpec,
        fn: Callable[[], tuple[T, Usage]],
        describe: Callable[[T], dict[str, Any]],
        *,
        notes: list[str] | None = None,
        **data: Any,
    ) -> T | None:
        """One role call, booked whatever happens. None when it failed, after telling the
        investor; a failure is also a note, so the sheet is never shown as if it had been
        reviewed."""
        self.say(f"Asking the {spec.name}...")
        try:
            value, usage = fn()
        except RoleError as exc:
            why = _one_line(str(exc).removeprefix(f"{exc.role}: "), 300)
            return self._failed(spec, exc.usage, str(exc.outcome), why, notes, data)
        except (ValueError, OSError) as exc:  # refused before any call was made: nothing spent
            return self._failed(
                spec, Usage(0, 0, 0, 0), "not_called", _one_line(str(exc), 300), notes, data
            )
        self._book(spec, usage, "completed", "ok", **describe(value) | data)
        return value

    def _failed(
        self,
        spec: RoleSpec,
        usage: Usage,
        outcome: str,
        why: str,
        notes: list[str] | None,
        data: dict[str, Any],
    ) -> None:
        self._book(spec, usage, outcome, "failed", detail=why, **data)
        self.say(f"The {spec.name} failed ({why}); the run goes on without its output.")
        if notes is not None:
            notes.append(
                f"{spec.name}: FAILED ({why}). No opinion was given; that is not a clean result."
            )
        return None

    def record_start(self, config: FirmConfig) -> None:
        """Write the run's `started` event with the chosen roles on it. `run_firm` then finds it
        and writes none, so the two never disagree. Nothing is written without roles."""
        if self.setup.roles:
            data = {"config": config_data(config), "roles": self.setup.data()}
            Recorder(self.ledger, self.run_id, 0)("boss", EventType.STARTED, data=data)

    # --- stage 1: before the investor approves the term sheet -------------------------------

    def plan(
        self,
        idea: str,
        budget_micros: int,
        *,
        max_tasks: int,
        n_rounds: int,
        draft_boss: Callable[[], TermSheet | None],
    ) -> Plan | None:
        """The sheet to show the investor, with the roles' notes. `draft_boss` is the boss's single
        call; it is made only when the staged draft is not, and None (nothing to approve) is what
        it returns when it failed."""
        notes: list[str] = []
        stories = self._stories(idea, notes) if self._on("product_manager") else None
        if stories is not None and self._on("user_agent"):
            self._user_agent(idea, stories, notes)
        staged = self._on("system_designer") and self._on("tester")
        sheet = None
        if stories is not None and staged:
            sheet = self._staged(idea, budget_micros, stories, max_tasks, n_rounds, notes)
        elif staged:
            self.say("There are no stories, so the staged draft cannot run: the boss drafts alone.")
        if sheet is None:
            sheet = draft_boss()
            if sheet is None:
                return None
        if self._on("check_auditor"):
            self._audit(sheet, notes)
        if stories is not None and self._on("judge"):
            self._judge_stories(idea, stories, notes)
        return Plan(sheet, tuple(f"\n{note}" for note in notes))  # a blank line sets each apart

    def _stories(self, idea: str, notes: list[str]) -> Stories | None:
        stories = self._call(
            _spec("product_manager"),
            lambda: write_stories(idea, **self._call_args()),
            lambda s: {"detail": f"{len(s.stories)} stories, {len(s.criteria())} criteria"},
            notes=notes,
        )
        if stories is None:
            return None
        (self.paths.root / "stories.json").write_text(
            json.dumps(stories.to_data(), indent=2), encoding="utf-8"
        )
        text = safe_text(stories_text(stories), limit=_STORIES_CHARS)
        notes.append(f"Stories the product manager wrote (saved as stories.json):\n{text}")
        gaps = [_one_line(f, 200) for f in uncovered_fragments(idea, stories)]
        if gaps:
            notes.append(
                "Parts of your idea no acceptance criterion quotes:\n"
                + "\n".join(f"  - {g}" for g in gaps)
            )
        else:
            notes.append("Every part of your idea is quoted by an acceptance criterion.")
        return stories

    def _user_agent(self, idea: str, stories: Stories, notes: list[str]) -> None:
        review = self._call(
            _spec("user_agent"),
            lambda: review_stories(idea, stories, **self._call_args()),
            lambda r: {"detail": f"{len(r.missing)} missing, {len(r.misread)} misread"},
            notes=notes,
        )
        if review is not None:
            notes.append(_render_review(review))

    def _staged(
        self,
        idea: str,
        budget_micros: int,
        stories: Stories,
        max_tasks: int,
        n_rounds: int,
        notes: list[str],
    ) -> TermSheet | None:
        self.say("Asking the system_designer and the tester...")
        try:
            draft = draft_staged(
                idea,
                budget_micros,
                self.paths.checks,
                stories=stories,
                max_tasks=max_tasks,
                n_rounds=n_rounds,
                **self._call_args(),
            )
        except StagedDraftError as exc:
            why = _one_line("; ".join(exc.problems), 300)
            for name, usage in exc.paid.items():
                if name == exc.stage:
                    self._book(_spec(name), usage, str(exc.outcome), "failed", detail=why)
                else:
                    unused = f"not used: the staged draft failed at {exc.stage}"
                    self._book(_spec(name), usage, "completed", "unused", detail=unused)
            shutil.rmtree(self.paths.checks, ignore_errors=True)  # the boss's draft starts clean
            line = f"The staged draft failed at {exc.stage} ({why}); the boss drafts alone instead."
            self.say(line)
            notes.append(line)
            return None
        n_tasks, n_checks = len(draft.design.tasks), len(draft.plan.checks)
        self._book(
            _spec("system_designer"),
            draft.designer_usage,
            "completed",
            "ok",
            detail=f"{n_tasks} task(s)",
        )
        self._book(
            _spec("tester"), draft.tester_usage, "completed", "ok", detail=f"{n_checks} checks"
        )
        notes.append(
            "Which check covers which acceptance criterion:\n"
            + render_coverage(stories, draft.plan.checks, draft.plan.untestable)
        )
        return draft.sheet

    def _audit(self, sheet: TermSheet, notes: list[str]) -> None:
        audit = self._call(
            _spec("check_auditor"),
            lambda: audit_checks(sheet.idea, sheet.checks, self.paths.checks, **self._call_args()),
            lambda a: {"detail": f"{len(a.flagged)} of {len(a.verdicts)} checks flagged"},
            notes=notes,
        )
        if audit is not None:
            notes.append("Check auditor's opinion of each check:\n" + render_audit(audit))

    def _calibration(self, rubric_id: str) -> Any:
        from boss.roles.judge import Calibration, CalibrationError

        path = self.project / ".boss" / "calibration" / f"{rubric_id}.json"
        if not path.is_file():
            return None
        try:
            return Calibration.load(path)
        except CalibrationError as exc:
            self.say(f"Calibration file {path} is unusable ({_one_line(str(exc), 200)}): not used.")
            return None

    def _judge(
        self, rubric_id: str, artifact: str, idea: str, notes: list[str] | None
    ) -> str | None:
        """The rendered judgement of `artifact`, or None. It gates nothing, calibrated or not."""
        # judge.py imports boss.cli for its calibration command, so importing it at the top of
        # this module (which cli imports) would be circular.
        from boss.roles.judge import judge_artifact, load_rubric, render_judgement

        rubric = load_rubric(rubric_id)
        judgement = self._call(
            _spec("judge"),
            lambda: judge_artifact(
                rubric,
                artifact,
                idea,
                calibration=self._calibration(rubric_id),
                **self._call_args(),
            ),
            lambda j: {
                "detail": f"mean {j.mean:.1f}, {'calibrated' if j.calibrated else 'uncalibrated'}",
                "calibrated": j.calibrated,
            },
            notes=notes,
            rubric=rubric_id,
        )
        return None if judgement is None else render_judgement(judgement)

    def _judge_stories(self, idea: str, stories: Stories, notes: list[str]) -> None:
        text = self._judge("stories", stories_text(stories), idea, notes)
        if text is not None:
            notes.append("Judge's score of the stories (advisory, gates nothing):\n" + text)

    # --- stage 2: while the loop runs --------------------------------------------------------

    def advisor(self, sheet: TermSheet) -> Advise | None:
        """What `run_firm` asks for one line before it puts a dispute to the investor."""
        if not self._on("consultant"):
            return None
        by_id = {c.id: c for c in sheet.checks}

        def advise(check_id: str, worker_reason: str) -> str | None:
            check = by_id.get(check_id)
            if check is None:
                return None
            advice = self._call(
                _spec("consultant"),
                lambda: advise_on_dispute(
                    sheet.idea,
                    check.description,
                    (self.paths.checks / check.file).read_text(encoding="utf-8"),
                    worker_reason,
                    **self._call_args(),
                ),
                lambda a: {"detail": f"{a.recommendation} {check_id}"},
                check=check_id,
            )
            return None if advice is None else render_advice(advice)

        return advise


def _render_review(review: StoryReview) -> str:
    head = f"User agent's opinion of the stories, unverified: {_one_line(review.verdict, 20)}"
    if not review.missing and not review.misread:
        return head + "; it found nothing missing or misread."
    lines = [head]
    lines += [
        f'  missing: "{_one_line(m.quote, 240)}" | why: {_one_line(m.why, 240)}'
        for m in review.missing
    ]
    lines += [
        f"  misread {_one_line(m.criterion, 12)}: "
        f'"{_one_line(m.quote, 240)}" | why: {_one_line(m.why, 240)}'
        for m in review.misread
    ]
    return "\n".join(lines)


def _one_line(text: str, limit: int) -> str:
    return safe_text(" ".join(text.split()), limit=limit)
