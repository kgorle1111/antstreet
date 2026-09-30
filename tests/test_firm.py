"""The round loop end to end, with a scripted worker and the real gate. No model calls."""

import time

import pytest

from boss.approval import NotApprovedError, content_hashes
from boss.boss import load_prompt
from boss.errors import Outcome
from boss.firm import FirmConfig, run_firm
from boss.gate import run_gate
from boss.ledger import Event, EventType, LedgerWriter, read_events, total
from boss.limits import RunLimits
from boss.report import build_report, render_report
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
    """A scripted worker. Each step is (file, source, status, outcome, cost, disputes, denials)."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.specs = []
        self.totals = {}

    def __call__(self, spec, workspace, log_path, *, env):
        self.specs.append(spec)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        name, code, status, outcome, cost, disputes, denials = step
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
            status={"status": status, "reason": f"scripted {status}"}
            | ({"disputed_checks": disputes} if disputes else {}),
            session_id=session,
            exit_code=0,
            duration_s=0.1,
            log_path=log_path,
            denials=[{"tool": tool, "reason": "rule"} for tool in denials],
        )


def step(
    code,
    status="continuing",
    outcome=Outcome.COMPLETED,
    cost=10_000,
    name="rev.py",
    disputes=(),
    denials=(),
):
    return (name, code, status, outcome, cost, list(disputes), list(denials))


def dispute(check, reason="the idea says otherwise"):
    return {"check": check, "reason": reason}


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


def run(
    paths,
    worker,
    s=None,
    *,
    approved=True,
    answers=(),
    config=None,
    sleeps=None,
    gate=run_gate,
    clock=time.monotonic,
):
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
            gate=gate,
            clock=clock,
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
        assert spec.append_system_prompt == load_prompt("builder_v3.md")
    assert "source of truth" in load_prompt("builder_v3.md")
    assert [e.data["prompt"] for e in events_of(paths, EventType.HIRED)] == ["builder_v3.md"] * 2


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


def test_a_slice_cap_holds_back_the_reserve_so_an_overshoot_stays_inside_the_round(paths):
    # 150,000 with a 100,000 reserve funds a 50,000 cap. The worker runs one response past its cap
    # and spends 140,000; the round is still inside its budget and cannot fund another slice.
    s = sheet(rounds=(Round(1, 150_000, 2),))
    worker = Script(step(HALF, cost=140_000), step(GOOD, "done"))
    report, said = run(paths, worker, s, config=FirmConfig(slice_micros=100_000))
    assert not report.all_passed
    assert len(worker.specs) == 1
    assert events_of(paths, EventType.SLICE_START)[0].data["cap_micros"] == 50_000
    assert total(read_events(paths.ledger)).cost_micros == 140_000 <= s.budget_micros
    [line] = [line for line in said if "cannot fund another slice" in line]
    assert "$0.01 left" in line and "$0.1 of it reserved" in line


def test_nobody_is_hired_into_a_round_that_cannot_fund_a_slice(paths):
    s = sheet(rounds=(Round(1, 104_999, 2),))  # one micro short of reserve + minimum slice
    worker = Script(step(GOOD, "done"))
    report, _ = run(paths, worker, s)
    assert worker.specs == [] and events_of(paths, EventType.HIRED) == []
    assert report.passed == 0


def test_the_reserve_is_configurable(paths):
    s = sheet(rounds=(Round(1, 104_999, 2),))
    worker = Script(step(GOOD, "done", cost=90_000))
    config = FirmConfig(slice_micros=100_000, reserve_micros=20_000)
    report, _ = run(paths, worker, s, config=config)
    assert report.all_passed
    assert events_of(paths, EventType.SLICE_START)[0].data["cap_micros"] == 84_999


def test_next_round_needs_the_investor_and_then_continues(paths):
    s = sheet(rounds=(Round(1, 204_000, 1), Round(2, 300_000, 2)))
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
    s = sheet(rounds=(Round(1, 204_000, 1), Round(2, 300_000, 2)))
    worker = Script(step(HALF, cost=100_000), step(GOOD, "done"))
    report, _ = run(paths, worker, s, answers=["n"])
    assert report.stopped == "investor declined the round"
    assert len(worker.specs) == 1
    assert events_of(paths, EventType.STOPPED)[0].actor == "investor"


def test_round_below_its_unlock_threshold_stops_the_run(paths):
    s = sheet(rounds=(Round(1, 204_000, 2), Round(2, 300_000, 2)))
    worker = Script(step(HALF, cost=100_000))
    report, said = run(paths, worker, s)
    assert report.stopped == "round 1 closed below its unlock threshold"
    assert len(worker.specs) == 1
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
    assert len({s.session_id for s in worker.specs}) == 3  # a fresh session id per attempt
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
    # 404,000 funds three slices that each spend 100,000, leaving 104,000: 4,000 above the
    # reserve, below the 5,000 minimum slice. The stalled worker is fired with no money to
    # replace it.
    s = sheet(rounds=(Round(1, 404_000, 2),))
    worker = Script(*[step(HALF, cost=100_000)] * 3)
    report, _ = run(paths, worker, s)
    assert len(events_of(paths, EventType.FIRED)) == 1
    assert events_of(paths, EventType.HIRED)[-1].data["worker"] == "w1"
    assert (report.passed, report.total) == (1, 2)
    assert (paths.product / "rev.py").read_text() == HALF
    assert events_of(paths, EventType.ROUND_CLOSED)[0].data["passed"] == 1


# Disputed checks: a worker that believes a check is wrong sends it to the investor.


def test_a_worker_disputing_its_only_failing_check_is_set_aside_not_fired(paths):
    worker = Script(step(HALF, disputes=[dispute("c01")]), step(GOOD, "done"))
    report, said = run(paths, worker)
    [disputed] = events_of(paths, EventType.DISPUTED)
    assert disputed.actor == "worker:w1"
    assert disputed.data == {
        "task": "t1",
        "check": "c01",
        "reason": "the idea says otherwise",
        "worker": "w1",
        "slice": 1,
    }
    assert events_of(paths, EventType.FIRED) == [] and events_of(paths, EventType.BLOCKED) == []
    [aside] = events_of(paths, EventType.ABANDONED)
    assert aside.data == {"task": "t1", "reason": "disputed"}
    assert len(worker.specs) == 1  # no second slice is funded, and nobody replaces the worker
    assert "Task t1 is set aside: its worker disputes c01. See the report." in said


def test_disputing_a_check_never_counts_it_as_passing_or_unlocks_a_round(paths):
    s = sheet(rounds=(Round(1, 250_000, 2), Round(2, 250_000, 2)))
    report, said = run(paths, Script(step(HALF, "done", disputes=[dispute("c01")])), s)
    assert (report.passed, report.total) == (1, 2) and not report.all_passed
    assert report.stopped == "round 1 closed below its unlock threshold"
    [closed] = events_of(paths, EventType.ROUND_CLOSED)
    assert closed.data == {"passed": 1, "total": 2, "unlocked": False}
    assert not any(line.startswith("Round 2") for line in said)


def test_a_worker_that_disputes_everything_is_fired_and_replaced_like_any_stalled_worker(paths):
    everything = [dispute("c01"), dispute("c02")]
    worker = Script(step(None, disputes=everything), step(None), step(GOOD, "done"))
    report, _ = run(paths, worker)
    assert [e.data["check"] for e in events_of(paths, EventType.DISPUTED)] == ["c01", "c02"]
    assert events_of(paths, EventType.FIRED)[0].data["reason"] == "no progress"
    assert events_of(paths, EventType.ABANDONED) == []
    assert report.all_passed  # the replacement did the work the first worker disputed away


def test_a_dispute_does_not_stop_work_on_the_other_checks(paths):
    # c01 is disputed while c02 still fails, so the worker is funded again; its next brief names
    # the dispute, and repeating the dispute does not record it twice.
    worker = Script(
        step(BAD, disputes=[dispute("c01")]),
        step(HALF, disputes=[dispute("c01", "still wrong")]),
        step(GOOD, "done"),
    )
    report, _ = run(paths, worker)
    assert len(worker.specs) == 2
    assert "You disputed: c01." in worker.specs[1].prompt
    assert [e.data["slice"] for e in events_of(paths, EventType.DISPUTED)] == [1]
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "disputed"
    assert report.passed == 1


def test_only_a_failing_check_of_the_workers_own_task_can_be_disputed(paths):
    # c02 passes, c03 belongs to the other task, c77 does not exist: none of them is recorded,
    # so the worker is judged as if it had disputed nothing.
    disputes = [dispute("c02"), dispute("c03"), dispute("c77")]
    worker = Script(
        step(HALF, disputes=disputes),
        step(HALF, disputes=disputes),
        step(HALF, disputes=disputes),
        step(GOOD, "done"),
        step("def shout(s):\n    return s.upper() + '!'\n", "done", name="up.py"),
    )
    report, _ = run(paths, worker, sheet(two_tasks=True))
    assert events_of(paths, EventType.DISPUTED) == []
    assert events_of(paths, EventType.FIRED)[0].data["reason"] == "no progress"
    assert report.all_passed


def test_a_disputed_check_that_later_passes_finishes_the_task(paths):
    worker = Script(step(BAD, disputes=[dispute("c01")]), step(GOOD, "done"))
    report, _ = run(paths, worker)
    assert report.all_passed
    assert events_of(paths, EventType.ABANDONED) == []


def test_disputes_survive_a_resume_and_reach_the_board_report(paths):
    first = Script(step(BAD, disputes=[dispute("c01", "idea says raise")]), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(paths, first)
    # The run is resumed from the ledger alone: the dispute is still known, the worker is
    # funded again for c02, and its brief names the dispute.
    assert events_of(paths, EventType.ABANDONED) == []
    worker = Script(step(HALF))
    worker.totals = dict(first.totals)
    run(paths, worker)
    assert "You disputed: c01." in worker.specs[0].prompt
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "disputed"
    text = build_report(read_events(paths.ledger))
    assert [(d.check, d.reason) for d in text.disputes] == [("c01", "idea says raise")]


# Approval is bound to the check files' content and verified every time they are used.


class Tampering:
    """Wraps a scripted worker; edits a check file on disk after the chosen slice."""

    def __init__(self, worker, check_file, after_slice=1):
        self.worker, self.check_file, self.after_slice = worker, check_file, after_slice

    def __call__(self, spec, workspace, log_path, *, env):
        result = self.worker(spec, workspace, log_path, env=env)
        if len(self.worker.specs) == self.after_slice:
            self.check_file.write_text("def test_anything():\n    pass\n")
        return result


def test_a_check_edited_mid_run_stops_the_run_and_its_result_is_never_recorded(paths):
    # The edited c01 would pass on anything. Without the control the gate would record a pass.
    worker = Script(step(HALF, cost=30_000), step(HALF))
    report, _ = run(paths, Tampering(worker, paths.checks / "test_c01.py"))
    assert report.stopped == (
        "stopped: the term sheet or a check changed after the investor approved it"
    )
    assert report.passed == 0 and events_of(paths, EventType.CHECK_RESULT) == []
    [stop] = events_of(paths, EventType.STOPPED)
    assert stop.actor == "rule"
    assert len(worker.specs) == 1  # nothing more is funded
    assert total(read_events(paths.ledger)).cost_micros == 30_000  # the slice is still on the books


def test_a_check_edited_between_slices_stops_the_run_before_the_next_slice_is_paid_for(paths):
    def gate_then_tamper(workspace, checks_dir, checks):
        results = run_gate(workspace, checks_dir, checks)
        (checks_dir / "test_c02.py").write_text("def test_anything():\n    pass\n")
        return results

    worker = Script(step(BAD), step(GOOD, "done"))
    report, _ = run(paths, worker, gate=gate_then_tamper)
    assert report.stopped.startswith("stopped: the term sheet or a check changed")
    assert len(worker.specs) == 1  # slice 2 was never spawned
    assert len(events_of(paths, EventType.CHECK_RESULT)) == 2  # slice 1's honest results stand


def test_a_new_worker_is_never_briefed_from_a_check_edited_after_approval(paths):
    # The first brief quotes the check files from disk. The second task's check is edited after
    # the first task was gated, so its worker must not be spawned on the edited text.
    def gate_then_tamper(workspace, checks_dir, checks):
        results = run_gate(workspace, checks_dir, checks)
        (checks_dir / "test_c03.py").write_text("def test_anything():\n    pass\n")
        return results

    worker = Script(step(GOOD, "done"), step("def shout(s):\n    return s\n", name="up.py"))
    report, _ = run(paths, worker, sheet(two_tasks=True), gate=gate_then_tamper)
    assert report.stopped.startswith("stopped: the term sheet or a check changed")
    assert len(worker.specs) == 1
    assert (report.passed, report.total) == (2, 3)  # the first task's honest passes stand


def test_a_check_deleted_mid_run_stops_the_run_like_an_edited_one(paths):
    # Found by review: a missing check file escaped as FileNotFoundError, with no record of why.
    class Deleting(Tampering):
        def __call__(self, spec, workspace, log_path, *, env):
            result = self.worker(spec, workspace, log_path, env=env)
            self.check_file.unlink()
            return result

    worker = Script(step(HALF, cost=30_000), step(GOOD, "done"))
    report, _ = run(paths, Deleting(worker, paths.checks / "test_c01.py"))
    assert report.stopped.startswith("stopped: the term sheet or a check changed")
    assert events_of(paths, EventType.CHECK_RESULT) == [] and len(worker.specs) == 1
    assert total(read_events(paths.ledger)).cost_micros == 30_000


def test_a_resumed_run_stays_stopped_after_tampering_even_if_the_check_is_restored(paths):
    original = (paths.checks / "test_c01.py").read_text()
    worker = Script(step(HALF), step(GOOD, "done"))
    run(paths, Tampering(worker, paths.checks / "test_c01.py"))
    (paths.checks / "test_c01.py").write_text(original)
    resumed = Script(step(GOOD, "done"))
    report, _ = run(paths, resumed)
    assert report.stopped == "stopped earlier" and resumed.specs == []


# Hard limits: a second layer behind the round budget and the firing rule. One test trips each.
PATIENT = FiringPolicy(stall_slices=50, max_slices=50)


def rule_stops(paths):
    return [e.data["reason"] for e in events_of(paths, EventType.STOPPED) if e.actor == "rule"]


def test_the_slice_limit_stops_a_run_the_firing_rule_would_let_continue(paths):
    config = FirmConfig(policy=PATIENT, limits=RunLimits(max_slices=3))
    worker = Script(*[step(BAD, cost=1_000)] * 10)
    report, _ = run(paths, worker, config=config)
    assert len(worker.specs) == 3
    assert report.stopped == "stopped: 3 slices started; the run limit is 3"
    assert rule_stops(paths) == ["3 slices started; the run limit is 3"]
    assert events_of(paths, EventType.FIRED) == []


def test_the_worker_limit_stops_a_run_before_the_hire_that_would_exceed_it(paths):
    config = FirmConfig(limits=RunLimits(max_workers=1))
    worker = Script(step(BAD), step(BAD), step(GOOD, "done"))
    report, _ = run(paths, worker, config=config)
    assert len(events_of(paths, EventType.FIRED)) == 1
    assert len(events_of(paths, EventType.HIRED)) == 1 and len(worker.specs) == 2
    assert rule_stops(paths) == ["1 workers hired; the run limit is 1"]
    assert events_of(paths, EventType.REASSIGNED) == []


def test_the_worker_limit_is_not_tripped_by_a_task_that_will_be_abandoned_anyway(paths):
    config = FirmConfig(limits=RunLimits(max_workers=2))
    report, _ = run(paths, Script(step(BAD), step(BAD), step(BAD), step(BAD)), config=config)
    assert rule_stops(paths) == []
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "already reassigned once"


def test_the_wall_clock_limit_stops_the_run_before_its_next_slice(paths):
    ticks = iter([0.0, 10.0, 61.0, 999.0])  # run start, before slice 1, before slice 2
    config = FirmConfig(policy=PATIENT, limits=RunLimits(max_seconds=60))
    worker = Script(*[step(BAD)] * 5)
    report, _ = run(paths, worker, config=config, clock=lambda: next(ticks))
    assert len(worker.specs) == 1
    assert rule_stops(paths) == ["61s of wall clock elapsed; the run limit is 60s"]


def test_the_spend_ceiling_stops_a_run_whose_slice_ran_far_past_its_cap(paths):
    # Two rounds of 150,000 and 300,000 with a 100,000 reserve each: the ceiling is 650,000.
    # One slice spends 700,000. The investor funds round 2, and the run still stops.
    s = sheet(rounds=(Round(1, 150_000, 1), Round(2, 300_000, 2)))
    worker = Script(step(HALF, cost=700_000), step(GOOD, "done"))
    report, _ = run(paths, worker, s, answers=["y"])
    assert len(worker.specs) == 1
    assert rule_stops(paths) == ["spend $0.7 is over the run ceiling of $0.65"]
    assert report.stopped.startswith("stopped: spend $0.7")


def test_a_run_inside_every_limit_is_not_stopped_by_them(paths):
    config = FirmConfig(limits=RunLimits(max_slices=2, max_workers=1, max_seconds=60))
    report, _ = run(paths, Script(step(HALF), step(GOOD, "done")), config=config)
    assert report.all_passed and rule_stops(paths) == []


def test_a_run_stopped_by_a_limit_stays_stopped_when_resumed(paths):
    config = FirmConfig(policy=PATIENT, limits=RunLimits(max_slices=1))
    run(paths, Script(step(BAD), step(GOOD, "done")), config=config)
    resumed = Script(step(GOOD, "done"))
    report, _ = run(paths, resumed)
    assert report.stopped == "stopped earlier" and resumed.specs == []


def test_a_workers_words_are_made_safe_before_they_reach_the_ledger_or_the_report(paths):
    secret = "sk-ant-" + "k" * 40

    class Chatty(Script):
        def __call__(self, spec, workspace, log_path, *, env):
            run = super().__call__(spec, workspace, log_path, env=env)
            run.status["reason"] = f"\x1b]0;pwned\x07 blocked by {secret}"
            run.status["junk"] = "x" * 100_000
            return run

    run(paths, Chatty(step(None, "blocked")))
    ledger_text = paths.ledger.read_text()
    assert secret not in ledger_text and "\x1b" not in ledger_text
    assert len(ledger_text) < 20_000  # the 100,000 characters of junk were not kept
    [end] = events_of(paths, EventType.SLICE_END)
    assert end.data["status"] == {
        "status": "blocked",
        "reason": "\\x1b]0;pwned\\x07 blocked by [REDACTED]",
    }
    assert events_of(paths, EventType.BLOCKED)[0].data["reason"] == end.data["status"]["reason"]
    report = render_report(build_report(read_events(paths.ledger)))
    assert secret not in report and "\x1b" not in report


# Found in the rerun: a worker wrote to an absolute path outside its folder, was refused by the
# path rule, reported "blocked", and the task was set aside with nothing built.


def test_a_worker_blocked_by_a_refused_tool_call_is_told_why_and_funded_again(paths):
    worker = Script(step(None, "blocked", denials=["Write", "Read"]), step(GOOD, "done"))
    report, _ = run(paths, worker)
    assert report.all_passed
    assert events_of(paths, EventType.BLOCKED) == [] and events_of(paths, EventType.ABANDONED) == []
    assert events_of(paths, EventType.SLICE_END)[0].data["denied_tools"] == ["Read", "Write"]
    retry = worker.specs[1].prompt
    assert (
        "your Read, Write calls were refused because they named a path outside your folder" in retry
    )
    assert "for example `rev.py`" in retry
    assert "refused" not in worker.specs[0].prompt


def test_a_worker_that_stays_blocked_after_refusals_is_fired_by_the_stall_rule(paths):
    denied = step(None, "blocked", denials=["Write"])
    worker = Script(denied, denied, denied, denied)
    report, _ = run(paths, worker)
    assert [e.data["reason"] for e in events_of(paths, EventType.FIRED)] == ["no progress"] * 2
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "already reassigned once"


def test_blocked_without_a_refused_call_still_goes_to_the_investor(paths):
    worker = Script(step(None, "blocked", denials=["Write"]), step(None, "blocked"))
    run(paths, worker)
    assert len(worker.specs) == 2
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "blocked"
    assert "refused" in worker.specs[1].prompt


# Sessions. Probe (CLI 2.1.285): starting a session with an id that is already in use fails, and
# resuming one that was never created fails. So an id is used to start exactly once.


def test_an_attempt_interrupted_before_it_finished_is_started_again_under_a_new_session(paths):
    first = Script(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(paths, first)
    resumed = Script(step(GOOD, "done", cost=7_000))
    report, _ = run(paths, resumed)
    assert report.all_passed
    [spec] = resumed.specs
    assert spec.resume is False and spec.session_id != first.specs[0].session_id
    assert "> Reverse a string." in spec.prompt  # the first brief again, not a continuation
    starts = events_of(paths, EventType.SLICE_START)
    assert [e.data["slice"] for e in starts] == [1, 1]
    assert [e.data["session"] for e in starts] == [
        str(first.specs[0].session_id),
        str(spec.session_id),
    ]
    assert len(events_of(paths, EventType.HIRED)) == 1


def test_a_lost_slice_is_charged_to_the_round_at_its_cap(paths):
    # 305,000 funds a 100,000 slice that is interrupted, then another; the lost one is counted at
    # its cap, so after the second (100,000 spent) only the reserve and 5,000 are left.
    s = sheet(rounds=(Round(1, 305_000, 2),))
    with pytest.raises(KeyboardInterrupt):
        run(paths, Script(KeyboardInterrupt()), s)
    worker = Script(step(HALF, cost=100_000), step(HALF, cost=1_000), step(GOOD, "done"))
    run(paths, worker, s)
    caps = [e.data["cap_micros"] for e in events_of(paths, EventType.SLICE_START)]
    assert caps == [100_000, 100_000, 5_000]
    assert len(worker.specs) == 2


def test_a_resumed_slice_that_was_interrupted_resumes_the_same_session_and_recovers_its_cost(paths):
    first = Script(step(HALF, cost=5_000), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(paths, first)
    resumed = Script(step(GOOD, "done", cost=7_000))
    # The interrupted slice spent 2,000 that was never reported; the session's running total
    # carries it, so it lands on the next slice of that session.
    resumed.totals = {str(first.specs[0].session_id): 5_000 + 2_000}
    run(paths, resumed)
    [spec] = resumed.specs
    assert spec.resume is True and spec.session_id == first.specs[0].session_id
    assert [e.cost_micros for e in events_of(paths, EventType.SLICE_END)] == [5_000, 9_000]
