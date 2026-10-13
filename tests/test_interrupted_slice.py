"""R7: a slice the run never saw end is booked on resume as an event of unknown cost.

Readiness run k (ops/fund-readiness-2026-10-13.md, G11) killed `antstreet` 4 s into a slice: the
slice had a `slice_start` and nothing else, so its spend was on no ledger line and the report's
Spend read as a complete figure when it was not. The CLI was billed for that slice either way.
"""

import signal
import subprocess
import sys

import pytest

from antstreet import budget
from antstreet.approval import content_hashes
from antstreet.errors import Outcome
from antstreet.firm import INTERRUPTED_SLICE, STOPPED_PGID, run_firm
from antstreet.gate import CheckResult, CheckStatus
from antstreet.ledger import Event, EventType, LedgerWriter, read_events, total
from antstreet.report import build_report, render_report
from antstreet.rundir import RunPaths
from antstreet.runner import OrphanWorkerError, SliceRun, pgid_file
from antstreet.stream import Usage
from antstreet.termsheet import CheckSpec, Round, Task, TermSheet
from antstreet.worker import IsolationError

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
GOOD = "def reverse(s):\n    return s[::-1]\n"


def sheet() -> TermSheet:
    tasks = (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),)
    checks = (CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),)
    return TermSheet("Reverse a string.", 500_000, (Round(1, 500_000, 1),), checks, tasks, True)


def gate(workspace, checks_dir, checks):
    """Passes when the worker wrote the right function; no subprocess."""
    source = workspace / "rev.py"
    ok = source.exists() and "s[::-1]" in source.read_text()
    status = CheckStatus.PASSED if ok else CheckStatus.FAILED
    return [CheckResult(c.id, status, 0 if ok else 1, "", "", 0.0) for c in checks]


def worker(*steps):
    """Each step is an exception to raise or the cost of a slice that writes GOOD."""
    queue = list(steps)

    def run(spec, workspace, log_path, *, env):
        step = queue.pop(0)
        if isinstance(step, BaseException):
            raise step
        (workspace / "rev.py").write_text(GOOD)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return SliceRun(
            outcome=Outcome.COMPLETED,
            usage=Usage(step, 10, 5, 0),
            status={"status": "done", "reason": "wrote rev.py"},
            session_id=str(spec.session_id),
            exit_code=0,
            duration_s=0.1,
            log_path=log_path,
        )

    return run


def start(tmp_path):
    paths = RunPaths(tmp_path / "run")
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(C01)
    with LedgerWriter(paths.ledger) as ledger:
        data = {"hashes": content_hashes(sheet(), paths.checks)}
        ledger.append(
            Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
    return paths


def firm(paths, slice_runner):
    with LedgerWriter(paths.ledger) as ledger:
        return run_firm(
            sheet(), paths, ledger, "r1", env={"HOME": "/h"}, ask=lambda q: "n",
            say=lambda _: None, slice_runner=slice_runner, gate=gate, sleep=lambda _: None,
        )  # fmt: skip


def interrupted(events):
    return [e for e in events if e.event is EventType.ERROR and INTERRUPTED_SLICE in e.data]


def test_a_slice_killed_mid_run_is_booked_as_unknown_cost_on_resume(tmp_path):
    paths = start(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        firm(paths, worker(KeyboardInterrupt()))  # `antstreet` dies while slice 1 runs
    killed = read_events(paths.ledger)
    assert [e.event for e in killed][-1] is EventType.SLICE_START
    assert total(killed).unknown_cost_events == 0  # the gap R7 closes: nothing says it is low
    charged = budget.remaining(sheet(), killed, 1)

    report = firm(paths, worker(6_000))
    assert report.all_passed
    events = read_events(paths.ledger)
    [booked] = interrupted(events)
    assert booked.actor == "worker:w1" and booked.round == 1
    assert booked.cost_micros is None  # unknown, never $0
    assert booked.data == {INTERRUPTED_SLICE: 1}
    # booked right after the lost start, before the slice that replaced it
    at = events.index(booked)
    assert events[at - 1].event is EventType.SLICE_START and events[at + 1].event is (
        EventType.SLICE_START
    )
    assert total(events).unknown_cost_events == 1 and total(events).cost_micros == 6_000
    # The booking moves no money: the round was already charged the lost slice's cap.
    assert budget.remaining(sheet(), events[: at + 1], 1) == charged
    text = render_report(build_report(events))
    assert "$0.0060 + 1 event(s) of unknown cost" in text
    assert "worker:w1 error (interrupted_slice=1)" in text


def test_resuming_again_books_nothing_twice(tmp_path):
    paths = start(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        firm(paths, worker(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        firm(paths, worker(KeyboardInterrupt()))  # killed again, in the restarted slice 1
    firm(paths, worker(6_000))
    before = read_events(paths.ledger)
    firm(paths, worker())  # a finished run: nothing runs, nothing is booked
    events = read_events(paths.ledger)
    assert events == before
    assert [e.data[INTERRUPTED_SLICE] for e in interrupted(events)] == [1, 1]
    assert total(events).unknown_cost_events == 2


def test_a_slice_that_ended_or_failed_isolation_is_not_booked_again(tmp_path):
    # The isolation failure already wrote an `error` of unknown cost in place of a `slice_end`.
    paths = start(tmp_path)
    with pytest.raises(IsolationError):
        firm(paths, worker(IsolationError("tools differ")))
    firm(paths, worker(6_000))  # the stop holds (only the investor lifts it): nothing runs
    events = read_events(paths.ledger)
    assert interrupted(events) == []
    assert [e.event for e in events].count(EventType.ERROR) == 1
    assert total(events).unknown_cost_events == 1


def left_running(paths, *marker):
    """A process in a session of its own, recorded as the slice's worker group, as a killed
    `antstreet` leaves it; `marker` goes on its command line."""
    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", *marker], start_new_session=True
    )
    pgid_file(paths.log("w1")).write_text(f"{sleeper.pid}\n")
    return sleeper


def killed_mid_slice(tmp_path):
    paths = start(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        firm(paths, worker(KeyboardInterrupt()))
    paths.log("w1").parent.mkdir(parents=True, exist_ok=True)
    [start_] = [e for e in read_events(paths.ledger) if e.event is EventType.SLICE_START]
    return paths, start_.data["session"]


def test_a_worker_still_running_is_stopped_before_its_slice_is_booked_and_run_again(tmp_path):
    paths, session = killed_mid_slice(tmp_path)
    orphan = left_running(paths, "--session-id", session)
    seen = []
    replacement = worker(6_000)

    def run(spec, workspace, log_path, *, env):
        seen.append(orphan.poll())  # the orphan was stopped (and only then) a slice runs again
        return replacement(spec, workspace, log_path, env=env)

    try:
        assert firm(paths, run).all_passed
    finally:
        orphan.kill()
    assert seen == [-signal.SIGTERM]
    [booked] = interrupted(read_events(paths.ledger))
    assert booked.data == {INTERRUPTED_SLICE: 1, STOPPED_PGID: orphan.pid}
    assert not pgid_file(paths.log("w1")).exists()


def test_a_live_group_that_is_not_the_workers_is_never_signalled_and_nothing_is_booked(tmp_path):
    paths, _ = killed_mid_slice(tmp_path)
    stranger = left_running(paths, "--session-id", "not-this-slice")  # the id was reused
    before = read_events(paths.ledger)
    try:
        with pytest.raises(OrphanWorkerError, match=rf"process group {stranger.pid} may still"):
            firm(paths, worker(6_000))
        assert stranger.poll() is None  # alive: an unverified process is never killed
    finally:
        stranger.kill()
        stranger.wait()
    assert read_events(paths.ledger) == before  # nothing booked, nobody hired, nothing run
    assert pgid_file(paths.log("w1")).exists()  # the refusal holds until a human acts


def test_a_recorded_group_that_has_ended_changes_nothing(tmp_path):
    # As a run older than the recorded group (no file): the slice is booked as it always was.
    paths, session = killed_mid_slice(tmp_path)
    ended = left_running(paths, "--session-id", session)
    ended.kill()
    ended.wait()
    assert firm(paths, worker(6_000)).all_passed
    [booked] = interrupted(read_events(paths.ledger))
    assert booked.data == {INTERRUPTED_SLICE: 1}
    assert not pgid_file(paths.log("w1")).exists()
