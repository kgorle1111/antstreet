"""The round loop end to end, with a scripted worker and the real gate. No model calls."""

import pytest

from boss.approval import NotApprovedError, content_hashes
from boss.boss import load_prompt
from boss.errors import Outcome
from boss.firm import FirmConfig, run_firm
from boss.ledger import Event, EventType, LedgerWriter, read_events, total
from boss.report import build_report
from boss.rule import FiringPolicy
from boss.rundir import RunPaths
from boss.runner import SliceRun
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, Task, TermSheet
from boss.worker import IsolationError

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
C02 = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
C03 = "from up import shout\n\ndef test_shout():\n    assert shout('a') == 'A!'\n"
GOOD = "def reverse(s):\n    return s[::-1]\n"
HALF = "def reverse(s):\n    return s\n"  # passes the empty-string check only
BAD = "def reverse(s):\n    raise RuntimeError\n"
ENV = {"HOME": "/h"}


def sheet(rounds=None, two_tasks=False) -> TermSheet:
    rounds = rounds or (Round(1, 500_000, 2),)
    checks = [
        CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
        CheckSpec("c02", "empty string", "test_c02.py", "t1"),
    ]
    tasks = [Task("t1", "Create rev.py with reverse(s).", ("rev.py",))]
    if two_tasks:
        checks.append(CheckSpec("c03", "shouts", "test_c03.py", "t2"))
        tasks.append(Task("t2", "Create up.py with shout(s).", ("up.py",)))
        rounds = (Round(1, 500_000, 3),)
    budget = sum(r.budget_micros for r in rounds)
    return TermSheet("Reverse a string.", budget, tuple(rounds), tuple(checks), tuple(tasks), True)


class Script:
    """A scripted worker. Each step is (file name, source or None, status, outcome, slice cost)."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.specs = []
        self.totals = {}

    def __call__(self, spec, workspace, log_path, *, env):
        self.specs.append(spec)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        name, code, status, outcome, cost = step
        if code is not None:
            (workspace / name).write_text(code)
        session = str(spec.session_id)
        if cost is not None:
            self.totals[session] = self.totals.get(session, 0) + cost
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("{}\n")
        return SliceRun(
            outcome=outcome,
            usage=Usage(self.totals.get(session) if cost is not None else None, 10, 5, 0),
            status={"status": status, "reason": f"scripted {status}"},
            session_id=session,
            exit_code=0,
            duration_s=0.1,
            log_path=log_path,
        )


def step(code, status="continuing", outcome=Outcome.COMPLETED, cost=10_000, name="rev.py"):
    return (name, code, status, outcome, cost)


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


def run(paths, worker, s=None, *, approved=True, answers=(), config=None, sleeps=None):
    s = s or sheet()
    replies = iter(answers)
    said = []

    def ask(question):
        said.append(question)
        return next(replies)

    with LedgerWriter(paths.ledger) as ledger:
        if approved and not paths.ledger.read_text():
            data = {"hashes": content_hashes(s, paths.checks)}
            ledger.append(
                Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
            )
        report = run_firm(
            s,
            paths,
            ledger,
            "r1",
            env=ENV,
            config=config or FirmConfig(),
            ask=ask,
            say=said.append,
            slice_runner=worker,
            sleep=(sleeps if sleeps is not None else []).append,
        )
    return report, said


def kinds(paths):
    return [(e.actor, e.event) for e in read_events(paths.ledger)]


def events_of(paths, kind):
    return [e for e in read_events(paths.ledger) if e.event is kind]


def test_one_good_slice_finishes_the_task(paths):
    worker = Script(step(GOOD, "done"))
    report, _ = run(paths, worker)
    assert report.all_passed and report.stopped is None
    assert kinds(paths) == [
        ("investor", EventType.APPROVED),
        ("boss", EventType.HIRED),
        ("worker:w1", EventType.SLICE_START),
        ("worker:w1", EventType.SLICE_END),
        ("gate", EventType.CHECK_RESULT),
        ("gate", EventType.CHECK_RESULT),
        ("boss", EventType.ROUND_CLOSED),
    ]
    assert (paths.product / "rev.py").read_text() == GOOD
    assert worker.specs[0].resume is False


def test_second_slice_resumes_the_session_with_gate_feedback_and_costs_are_deltas(paths):
    worker = Script(step(HALF, cost=5_000), step(GOOD, "done", cost=7_000))
    report, _ = run(paths, worker)
    assert report.all_passed
    first, second = worker.specs
    assert second.resume is True and second.session_id == first.session_id
    assert "Passing: c02" in second.prompt and "Failing: c01" in second.prompt
    ends = events_of(paths, EventType.SLICE_END)
    assert [e.cost_micros for e in ends] == [5_000, 7_000]
    assert [e.data["session_total_micros"] for e in ends] == [5_000, 12_000]
    assert total(read_events(paths.ledger)).cost_micros == 12_000


def test_stalled_worker_is_fired_and_its_replacement_gets_the_files_and_notes(paths):
    worker = Script(step(BAD), step(BAD), step(GOOD, "done"))
    report, _ = run(paths, worker)
    assert report.all_passed
    [fired] = events_of(paths, EventType.FIRED)
    assert fired.actor == "rule"
    assert (fired.data["worker"], fired.data["reason"]) == ("w1", "no progress")
    assert fired.data["evidence"]["stalled_slices"] == 2
    [moved] = events_of(paths, EventType.REASSIGNED)
    assert moved.data == {"task": "t1", "from": "w1", "to": "w2"}
    replacement = worker.specs[2]
    assert replacement.resume is False
    assert replacement.session_id != worker.specs[0].session_id
    assert "The previous builder was stopped: no progress" in replacement.prompt
    assert "previous_attempt/" in replacement.prompt
    assert (paths.workspace("w2") / "previous_attempt" / "rev.py").read_text() == BAD
    assert not (paths.product / "previous_attempt").exists()


def test_every_worker_is_given_the_investors_idea_word_for_word(paths):
    # Pilot finding: workers saw only the boss's paraphrase and followed it where it was wrong.
    worker = Script(step(BAD), step(BAD), step(GOOD, "done"))
    run(paths, worker)
    first, _, replacement = worker.specs
    for spec in (first, replacement):
        assert "> Reverse a string." in spec.prompt
        assert spec.prompt.index("> Reverse a string.") < spec.prompt.index("Create rev.py")
        assert spec.append_system_prompt == load_prompt("builder_v2.md")
    assert "source of truth" in load_prompt("builder_v2.md")
    assert [e.data["prompt"] for e in events_of(paths, EventType.HIRED)] == ["builder_v2.md"] * 2


def test_a_task_is_reassigned_only_once_then_abandoned(paths):
    worker = Script(step(BAD), step(BAD), step(BAD), step(BAD))
    report, _ = run(paths, worker)
    assert not report.all_passed
    assert report.stopped == "round 1 closed below its unlock threshold"
    assert len(events_of(paths, EventType.FIRED)) == 2
    [abandoned] = events_of(paths, EventType.ABANDONED)
    assert abandoned.data == {"task": "t1", "reason": "already reassigned once"}
    assert worker.steps == []


def test_with_firing_off_a_stalled_worker_runs_to_the_slice_limit(paths):
    config = FirmConfig(firing=False, policy=FiringPolicy(stall_slices=1, max_slices=3))
    worker = Script(*[step(BAD)] * 6)
    run(paths, worker, config=config)
    reasons = [e.data["reason"] for e in events_of(paths, EventType.FIRED)]
    assert reasons == ["slice limit", "slice limit"]
    assert len(events_of(paths, EventType.SLICE_END)) == 6


def test_round_ends_when_the_next_slice_is_not_affordable(paths):
    # 104,000 funds one slice capped at 83,200 (25% headroom). After a 100,000 slice only 4,000
    # is left, which cannot fund the 5,000 minimum, so the round stops there.
    s = sheet(rounds=(Round(1, 104_000, 2),))
    worker = Script(step(HALF, cost=100_000), step(GOOD, "done"))
    report, said = run(paths, worker, s, config=FirmConfig(slice_micros=100_000))
    assert not report.all_passed
    assert len(worker.specs) == 1
    assert any("out of budget" in line for line in said)
    assert events_of(paths, EventType.SLICE_START)[0].data["cap_micros"] == 83_200


def test_next_round_needs_the_investor_and_then_continues(paths):
    s = sheet(rounds=(Round(1, 104_000, 1), Round(2, 300_000, 2)))
    worker = Script(step(HALF, cost=100_000), step(GOOD, "done"))
    report, said = run(paths, worker, s, answers=["y"])
    assert report.all_passed
    assert any(q.startswith("Round 2: 1/2 checks pass. Fund $0.3 more?") for q in said)
    approvals = [e.data.get("round") for e in events_of(paths, EventType.APPROVED)]
    assert approvals == [None, 2]
    closed = [(e.round, e.data["unlocked"]) for e in events_of(paths, EventType.ROUND_CLOSED)]
    assert closed == [(1, True), (2, True)]
    assert events_of(paths, EventType.SLICE_END)[1].round == 2


def test_investor_can_decline_a_round(paths):
    s = sheet(rounds=(Round(1, 104_000, 1), Round(2, 300_000, 2)))
    worker = Script(step(HALF, cost=100_000), step(GOOD, "done"))
    report, _ = run(paths, worker, s, answers=["n"])
    assert report.stopped == "investor declined the round"
    assert len(worker.specs) == 1
    assert events_of(paths, EventType.STOPPED)[0].actor == "investor"


def test_round_below_its_unlock_threshold_stops_the_run(paths):
    s = sheet(rounds=(Round(1, 104_000, 2), Round(2, 300_000, 2)))
    report, said = run(paths, Script(step(HALF, cost=100_000)), s)
    assert report.stopped == "round 1 closed below its unlock threshold"
    assert not any(line.startswith("Round 2") for line in said)


def test_blocked_worker_is_escalated_not_fired(paths):
    report, _ = run(paths, Script(step(None, "blocked")))
    assert events_of(paths, EventType.FIRED) == []
    [blocked] = events_of(paths, EventType.BLOCKED)
    assert blocked.data == {"task": "t1", "reason": "scripted blocked"}
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "blocked"
    assert not report.all_passed


def test_rate_limit_is_waited_out_and_never_counts_against_the_worker(paths):
    limited = step(None, outcome=Outcome.RATE_LIMITED, cost=None)
    sleeps = []
    worker = Script(limited, limited, step(GOOD, "done"))
    report, _ = run(paths, worker, sleeps=sleeps)
    assert report.all_passed
    assert len(sleeps) == 2 and sleeps[1] <= 120
    assert events_of(paths, EventType.FIRED) == []
    assert [s.resume for s in worker.specs] == [False, False, False]
    assert len(events_of(paths, EventType.CHECK_RESULT)) == 2


def test_login_failure_stops_the_run_with_a_fix(paths):
    report, _ = run(paths, Script(step(None, outcome=Outcome.LOGIN, cost=0)))
    assert report.stopped.startswith("stopped:")
    [stop] = events_of(paths, EventType.STOPPED)
    assert "claude auth login" in stop.data["fix"]


def test_nothing_is_spawned_without_approval(paths):
    worker = Script(step(GOOD, "done"))
    with pytest.raises(NotApprovedError):
        run(paths, worker, approved=False)
    assert worker.specs == []


def test_isolation_failure_is_recorded_and_stops_the_run(paths):
    with pytest.raises(IsolationError):
        run(paths, Script(IsolationError("2 hook event(s) ran")))
    events = read_events(paths.ledger)
    assert events[-2].event is EventType.ERROR and events[-2].cost_micros is None
    assert events[-1].event is EventType.STOPPED


def test_an_interrupted_run_resumes_from_the_ledger_without_double_spending(paths):
    worker = Script(step(HALF, cost=5_000), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(paths, worker)
    resumed = Script(step(GOOD, "done", cost=7_000))
    resumed.totals = dict(worker.totals)
    report, _ = run(paths, resumed)
    assert report.all_passed
    assert len(events_of(paths, EventType.HIRED)) == 1
    [spec] = resumed.specs
    assert spec.resume is True and spec.session_id == worker.specs[0].session_id
    ends = events_of(paths, EventType.SLICE_END)
    assert [(e.data["slice"], e.cost_micros) for e in ends] == [(1, 5_000), (2, 7_000)]


def test_two_tasks_get_separate_workspaces_and_one_product(paths):
    shout = "def shout(s):\n    return s.upper() + '!'\n"
    worker = Script(step(GOOD, "done"), step(shout, "done", name="up.py"))
    report, _ = run(paths, worker, sheet(two_tasks=True))
    assert report.all_passed and (report.passed, report.total) == (3, 3)
    assert "c03" not in worker.specs[0].prompt and "test_c03.py" in worker.specs[1].prompt
    assert sorted(p.name for p in paths.product.iterdir()) == ["rev.py", "up.py"]
    assert not (paths.workspace("w1") / "up.py").exists()
    tagged = {(e.data["check"], e.data["worker"]) for e in events_of(paths, EventType.CHECK_RESULT)}
    assert tagged == {("c01", "w1"), ("c02", "w1"), ("c03", "w2")}


def test_board_report_agrees_with_the_run_and_the_ledger(paths):
    report, _ = run(paths, Script(step(HALF, cost=5_000), step(GOOD, "done", cost=7_000)))
    events = read_events(paths.ledger)
    board = build_report(events)
    assert board.total.cost_micros == total(events).cost_micros == 12_000
    assert [c.status for c in board.checks] == ["passed", "passed"]
    assert (board.rounds[0].passed, board.rounds[0].unlocked) == (report.passed, True)
    assert board.workers[0].slices == 2


def test_a_fired_workers_progress_survives_when_nothing_is_left_for_a_replacement(paths):
    # 304,000 funds three slices that each spend 100,000, leaving 4,000: below the 5,000
    # minimum slice, so the stalled worker is fired with no money to replace it.
    s = sheet(rounds=(Round(1, 304_000, 2),))
    worker = Script(*[step(HALF, cost=100_000)] * 3)
    report, _ = run(paths, worker, s)
    assert len(events_of(paths, EventType.FIRED)) == 1
    assert events_of(paths, EventType.HIRED)[-1].data["worker"] == "w1"
    assert (report.passed, report.total) == (1, 2)
    assert (paths.product / "rev.py").read_text() == HALF
    assert events_of(paths, EventType.ROUND_CLOSED)[0].data["passed"] == 1
