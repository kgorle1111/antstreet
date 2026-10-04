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

import ast
import dataclasses
import functools
import json
import shutil
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from boss import spec as rulespec
from boss.approval import TERM_SHEET_FILE, _check_text, content_hashes
from boss.budget import RESERVE_MICROS
from boss.errors import Outcome
from boss.firm import Advise, FirmConfig, FirmReport, config_data
from boss.gate import Check, CheckStatus, GateError, run_gate
from boss.ledger import Event, EventType, LedgerWriter
from boss.redact import safe_text
from boss.roles import registry
from boss.roles.advisory import advise_on_dispute, audit_checks, render_advice, render_audit
from boss.roles.base import RoleError, RoleSpec, ledger_fields
from boss.roles.critic import Finding, Review, findings_as_checks, review_product, write_check_files
from boss.roles.delivery import USAGE_FILE, install_demo, write_demo
from boss.roles.engineering import StagedDraftError, draft_staged, render_coverage, stories_text
from boss.roles.examiner import EXAMINER, run_examiner
from boss.roles.product import StoryReview, review_stories, uncovered_fragments, write_stories
from boss.roles.spec_mapper import compare, map_rules, render_comparison
from boss.roles.stories import Stories
from boss.rulings import DECLINED
from boss.rundir import Recorder, RunPaths
from boss.state import run_state
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, TermSheet, TermSheetError, validate
from boss.worker import usd

Ask = Callable[[str], str]
Say = Callable[[str], None]
Rerun = Callable[[TermSheet], FirmReport | int]  # run the firm again on an amended sheet

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
YES = ("y", "yes", "a", "approve")
_DEMO_DIR = "demo"  # the installed files, kept because every run of the firm rebuilds product/
_STORIES_CHARS = 20_000


class RolesError(ValueError):
    """The roles asked for cannot be run. The message says what to change."""


# Roles chosen by their own option, never by --roles: the examiner's checks need a count.
BY_OPTION = {EXAMINER.name: "--held-out N"}


def parse_roles(text: str, known: Iterable[str]) -> tuple[str, ...]:
    """The role names in a `--roles a,b,c` list ("all" is every known role), sorted, or RolesError.
    Checked before anything is spent."""
    names_known = sorted(set(known) - set(BY_OPTION))
    names = {n.strip() for n in text.split(",") if n.strip()}
    if own := sorted(names & set(BY_OPTION)):
        raise RolesError(
            "; ".join(f"{n} is not chosen with --roles: use {BY_OPTION[n]}" for n in own) + "."
        )
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


def default_fix_budget(config: FirmConfig) -> int:
    """Two slices and one reserve: what one worker needs to fix a handful of findings."""
    return 2 * config.slice_micros + config.reserve_micros


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
            self._failed(spec, exc.usage, str(exc.outcome), why, notes, data)
            return None
        except (ValueError, OSError) as exc:  # refused before any call was made: nothing spent
            self._failed(
                spec, Usage(0, 0, 0, 0), "not_called", _one_line(str(exc), 300), notes, data
            )
            return None
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

    def examine(self, sheet: TermSheet, n: int, reserve_micros: int) -> bool:
        """Held-out checks for this run, before the investor's review: the examiner sees the idea
        and the names the product must expose, never a visible check's body. True when some were
        kept; it books its own call, in round 1."""
        return run_examiner(
            sheet,
            self.paths,
            self.ledger,
            self.run_id,
            n=n,
            env=self.env,
            model=self.setup.model,
            reserve_micros=reserve_micros,
            executable=self.executable,
            say=self.say,
        )

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
        reserve_micros: int = RESERVE_MICROS,
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
            sheet = self._staged(
                idea, budget_micros, stories, max_tasks, n_rounds, reserve_micros, notes
            )
        elif staged:
            self.say("There are no stories, so the staged draft cannot run: the boss drafts alone.")
        if sheet is None:
            sheet = draft_boss()
            if sheet is None:
                return None
        if self._on("check_auditor"):
            self._audit(sheet, notes)
        if self._on("spec_mapper"):
            self._spec_map(sheet, notes)
        if stories is not None and self._on("judge"):
            self._judge_stories(idea, stories, notes)
        return Plan(sheet, tuple(f"\n{note}" for note in notes))  # a blank line sets each apart

    def _stories(self, idea: str, notes: list[str]) -> Stories | None:
        stories = self._call(
            _spec("product_manager"),
            lambda: write_stories(idea, **self._call_args()),
            lambda s: {"detail": f"stories {len(s.stories)}, criteria {len(s.criteria())}"},
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
        reserve_micros: int,
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
                reserve_micros=reserve_micros,
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

    def _spec_map(self, sheet: TermSheet, notes: list[str]) -> None:
        """The mapper's opinion of which rules each check asserts, against what the boss cites.
        It needs the rule list that only `--spec` writes; without one it makes no call."""
        if not self.paths.rules.is_file():
            line = "spec_mapper: not run. It reads the idea's rules, which only --spec makes."
            self.say(line)
            notes.append(line)
            return
        try:
            rules = rulespec.load(self.paths.rules, sheet.idea)
        except rulespec.SpecError as exc:
            line = f"spec_mapper: not run: {_one_line(str(exc), 200)}"
            self.say(line)
            notes.append(line)
            return
        claims = {c.id: c.criteria for c in sheet.checks}

        def describe(mapped: Any) -> dict[str, Any]:
            over = len(compare(claims, mapped).overclaims)
            return {
                "detail": f"{len(mapped.exercises)} checks mapped, {over} citations unconfirmed"
            }

        mapped = self._call(
            _spec("spec_mapper"),
            lambda: map_rules(rules, sheet.checks, self.paths.checks, **self._call_args()),
            describe,
            notes=notes,
        )
        if mapped is not None:
            notes.append(render_comparison(compare(claims, mapped), rules))

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

    # --- stage 3: after the workers finish ---------------------------------------------------

    def after_build(
        self,
        sheet: TermSheet,
        outcome: FirmReport,
        rerun: Rerun,
        *,
        review_cycles: int,
        fix_micros: int,
    ) -> FirmReport | int:
        """The critic, then the demo, on whatever was built. An int is an exit code: the fix
        round was interrupted."""
        if not self.setup.roles or not self._built():
            return outcome
        if self._on("critic"):
            result = self._review(sheet, outcome, rerun, review_cycles, fix_micros)
            if isinstance(result, int):
                return result
            sheet, outcome = result
        if self._on("demo_writer") and outcome.all_passed:
            self._demo(sheet)
        return outcome

    def _built(self) -> bool:
        return any(p.is_file() for p in self.paths.product.rglob("*"))

    def _review(
        self, sheet: TermSheet, outcome: FirmReport, rerun: Rerun, cycles: int, fix_micros: int
    ) -> tuple[TermSheet, FirmReport] | int:
        # The ledger counts the cycles: a resumed run finds them there and adds none. A cycle with
        # findings counts once the investor's answer is on it; a Ctrl-C at the question leaves the
        # cycle open, so a resume asks the critic again (one more call) and offers the findings.
        while _settled(self._events()) < max(1, cycles):
            review = self._critic(sheet)
            if review is None or not review.verified:
                break
            amended = None
            if cycles == 0:
                self.say(
                    "--review-cycles is 0: the findings are in the report, no fix round is offered."
                )
            elif outcome.stopped:
                self.say(f"The run ended early ({outcome.stopped}): no fix round is offered.")
            else:
                amended = self._amend(sheet, review, fix_micros)
            if amended is None:
                record = Recorder(self.ledger, self.run_id, 0)
                record("investor", EventType.RULED, data={"ruling": DECLINED})
                break
            result = rerun(amended)
            if isinstance(result, int):
                return result
            sheet, outcome = amended, result
        return sheet, outcome

    def _critic(self, sheet: TermSheet) -> Review | None:
        cycle = len(_calls(self._events(), "critic")) + 1
        review = self._call(
            _spec("critic"),
            lambda: review_product(
                sheet.idea,
                self.paths.product,
                self._passing(sheet),
                self.paths.root / f"critic-{cycle}",
                **self._call_args(),
            ),
            lambda r: {
                "detail": f"{len(r.verified)} verified, {len(r.rejected)} rejected",
                "verified": len(r.verified),
                "rejected": len(r.rejected),
                "cycle": cycle,
            },
        )
        if review is not None:
            for f in review.verified:
                self.say(f"Critic verified a finding ({f.severity}): {f.claim}")
            self.say(
                f"Critic: {len(review.verified)} finding(s) verified by running their tests on the "
                f"product, {len(review.rejected)} rejected."
            )
        return review

    def _passing(self, sheet: TermSheet) -> list[str]:
        """Descriptions of the checks that pass on the assembled product, from the ledger."""
        events = self._events()
        last = _last_slice_end(events)
        passed = {
            e.data.get("check")
            for e in events[last:]
            if e.event is EventType.CHECK_RESULT
            and e.data.get("scope") == "product"
            and e.data.get("status") == "passed"
        }
        return [c.description for c in sheet.checks if c.id in passed]

    def _amend(self, sheet: TermSheet, review: Review, fix_micros: int) -> TermSheet | None:
        """The sheet the investor is asked to approve: the verified findings as checks, and a new
        last round that funds a worker to fix them. Records the approval when the investor says
        yes; the checks it wrote are removed again when the sheet is not approved."""
        checks = self._proposed(sheet, review)
        if not checks:
            return None
        n, rounds = _with_fix_round(
            sheet,
            fix_micros,
            len(sheet.checks) + len(checks),
            run_state(self._events(), [t.id for t in sheet.tasks]).approved_rounds,
        )
        amended = dataclasses.replace(
            sheet,
            checks=(*sheet.checks, *checks),
            rounds=rounds,
            budget_micros=sheet.budget_micros + fix_micros,
        )
        try:
            validate(amended, self.paths.checks)
        except TermSheetError as exc:
            problems = _one_line("; ".join(exc.problems), 250)
            self.say(f"The amended term sheet does not validate: {problems}")
            self._remove(checks)
            return None
        for c in checks:
            self.say(f"\nCheck {c.id} [{c.task}] {_one_line(c.description, 300)}")
            self.say(f"--- {self.paths.checks / c.file}")
            self.say(_check_text(self.paths.checks / c.file))
        if n <= len(sheet.rounds):
            self.say(
                f"\nThe fix round is round {n}, in the place of the first round that never opened. "
                "The rounds after it move up one number and keep their money; each still needs "
                "your yes, and the last now unlocks only when every check passes."
            )
        question = (
            f"Add these {len(checks)} checks and fund a fix round of ${usd(fix_micros)}? "
            "[y]es / [n]o "
        )
        try:
            answer = self.ask(question).strip().lower()
        except EOFError:  # nobody is there to approve it; Ctrl-C is an interruption, not a no
            answer = "n"
        except KeyboardInterrupt:  # the files were written for a sheet nobody approved
            self._remove(checks)
            raise
        if answer not in YES:
            self.say("No fix round. The findings are in the report only.")
            self._remove(checks)
            return None
        # The approval goes on the ledger before the sheet on disk changes: an interruption between
        # the two leaves the old, still approved sheet to resume, never a sheet nobody approved.
        data = {
            "hashes": content_hashes(amended, self.paths.checks, self.paths.rules),
            "round": n,
            "added_checks": [c.id for c in checks],
        }
        Recorder(self.ledger, self.run_id, n)("investor", EventType.APPROVED, data=data)
        approved = dataclasses.replace(amended, approved_by_investor=True)
        (self.paths.root / TERM_SHEET_FILE).write_text(approved.to_json())
        self.say("Approved. Funding a worker to fix them...")
        return approved

    def _proposed(self, sheet: TermSheet, review: Review) -> list[CheckSpec]:
        """A check file for each verified finding that a task owns and that fails on an empty
        workspace (as every approved check must). A finding that does not qualify is dropped, with
        a line saying why."""
        specs: list[CheckSpec] = []
        for f in review.verified:
            task = _owner(sheet, f)
            if task is None:
                self.say(
                    f"Finding not proposed ({f.claim}): no task owns the module its test imports."
                )
                continue
            one = Review((f,), (), ())
            spec = findings_as_checks(one, [*sheet.checks, *specs], task)[0]
            write_check_files(one, [spec], self.paths.checks)
            specs.append(spec)
        if not specs:
            return []
        try:
            with tempfile.TemporaryDirectory(prefix="boss_empty_ws_") as empty:
                results = run_gate(
                    Path(empty),
                    self.paths.checks,
                    [Check(s.id, s.file) for s in specs],
                    timeout_s=30.0,
                )
        except GateError as exc:
            self.say(f"The findings could not be checked against an empty workspace ({exc}).")
            self._remove(specs)
            return []
        kept = []
        for spec, result in zip(specs, results, strict=True):
            if result.status is CheckStatus.FAILED:
                kept.append(spec)
            else:
                self.say(
                    f"Finding not proposed as a check ({spec.description}): it does not fail on an "
                    "empty workspace, so it could not measure progress."
                )
                self._remove([spec])
        return kept

    def _remove(self, specs: Sequence[CheckSpec]) -> None:
        for spec in specs:
            (self.paths.checks / spec.file).unlink(missing_ok=True)

    def _demo(self, sheet: TermSheet) -> None:
        """A demo of the product, installed beside it, then a judgement of its usage note. Only
        for a product that passes every check; once per build of the product."""
        events = self._events()
        since = _last_slice_end(events)
        made = _calls(events[since:], "demo_writer")
        installed = made[-1].data.get("result") == "ok" if made else False
        if not made:
            installed = self._write_demo(sheet)
        elif installed:
            self._reinstall()
        judged = _calls(events[since:], "judge", rubric="usage")
        usage_file = self.paths.product / USAGE_FILE
        if self._on("judge") and installed and not judged and usage_file.is_file():
            note = self._judge("usage", usage_file.read_text(encoding="utf-8"), sheet.idea, None)
            if note is not None:
                self.say("Judge's score of USAGE.md (advisory, gates nothing):\n" + note)

    def _write_demo(self, sheet: TermSheet) -> bool:
        product = self.paths.product

        def make() -> tuple[Any, Usage]:
            demo, usage = write_demo(
                sheet.idea, product, self.paths.root / "demo_scratch", **self._call_args()
            )
            try:
                files = install_demo(demo, product)
                (self.paths.root / _DEMO_DIR).mkdir(exist_ok=True)
                for path in files:
                    shutil.copy2(path, self.paths.root / _DEMO_DIR / path.name)
            except OSError as exc:  # the call was paid for: book it as such
                raise RoleError(
                    "demo_writer",
                    f"the demo could not be installed: {exc}",
                    Outcome.COMPLETED,
                    usage,
                ) from exc
            return demo, usage

        demo = self._call(_spec("demo_writer"), make, lambda d: {"detail": "installed in product/"})
        if demo is not None:
            self.say(f"Demo installed in {product}: {USAGE_FILE} says how to use the product.")
        return demo is not None

    def _reinstall(self) -> None:
        saved = self.paths.root / _DEMO_DIR
        if (self.paths.product / USAGE_FILE).exists() or not saved.is_dir():
            return
        try:
            for path in saved.iterdir():
                shutil.copy2(path, self.paths.product / path.name)
        except OSError as exc:
            self.say(f"The demo could not be put back in product/: {exc}")

    def _events(self) -> list[Event]:
        return self.paths.events()


def _calls(events: Sequence[Event], role: str, **match: Any) -> list[Event]:
    """The role's `role_call` events, oldest first, whose data has every `match` value."""
    return [
        e
        for e in events
        if e.event is EventType.ROLE_CALL
        and e.data.get("role") == role
        and all(e.data.get(k) == v for k, v in match.items())
    ]


def _settled(events: Sequence[Event]) -> int:
    """Critic cycles that need nothing more: no verified finding to offer, or the investor's answer
    on the ledger (the amendment's approval, or a decline). A call followed by another critic call
    with no answer between was interrupted, and counts for nothing."""
    done, waiting = 0, False
    for e in events:
        if e.event is EventType.ROLE_CALL and e.data.get("role") == "critic":
            waiting = bool(e.data.get("verified"))
            done += not waiting
        elif waiting and e.actor == "investor" and _answers_fix_question(e):
            done, waiting = done + 1, False
    return done


def _answers_fix_question(event: Event) -> bool:
    if event.event is EventType.APPROVED:
        return "added_checks" in event.data
    return event.event is EventType.RULED and event.data.get("ruling") == DECLINED


def _with_fix_round(
    sheet: TermSheet, fix_micros: int, total_checks: int, approved: frozenset[int]
) -> tuple[int, tuple[Round, ...]]:
    """The fix round's number and the sheet's rounds with it in the place of the first round that
    never opened. The unopened rounds follow it, renumbered, each still asking for its own yes; the
    last one unlocks only when every check passes, as a sheet requires. The fix round goes last
    when every round opened, or when a later round was opened anyway (renumbering would move its
    events)."""
    first = next((i for i, r in enumerate(sheet.rounds) if r.n not in approved), len(sheet.rounds))
    if any(r.n in approved for r in sheet.rounds[first:]):
        first = len(sheet.rounds)
    rest = [Round(r.n + 1, r.budget_micros, r.unlock_checks) for r in sheet.rounds[first:]]
    unlock = rest[0].unlock_checks if rest else total_checks
    if rest:
        rest[-1] = dataclasses.replace(rest[-1], unlock_checks=total_checks)
    n = first + 1
    return n, (*sheet.rounds[:first], Round(n, fix_micros, unlock), *rest)


def _last_slice_end(events: Sequence[Event]) -> int:
    return max((i for i, e in enumerate(events) if e.event is EventType.SLICE_END), default=0)


def _owner(sheet: TermSheet, finding: Finding) -> str | None:
    """The task that owns the product module the finding's test imports; the only task if there is
    just one. None when no task does."""
    if len(sheet.tasks) == 1:
        return sheet.tasks[0].id
    modules = _imported(finding.test_code)
    for task in sheet.tasks:
        for path in map(PurePosixPath, task.paths):
            if path == PurePosixPath(".") or any(
                path in (PurePosixPath(m), PurePosixPath(f"{m}.py")) for m in modules
            ):
                return task.id
    return None


def _imported(code: str) -> set[str]:
    try:
        tree = ast.parse(code.removeprefix("﻿"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


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
