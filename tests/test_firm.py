"""The first round end to end, with a scripted fake worker and the real gate. No model calls."""

import pytest

from boss.approval import NotApprovedError, content_hashes
from boss.errors import Outcome
from boss.firm import RunPaths, run_first_round, task_prompt
from boss.ledger import Event, EventType, LedgerWriter, read_events, total
from boss.runner import SliceRun
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, Task, TermSheet
from boss.worker import IsolationError

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
C02 = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
SHEET = TermSheet(
    idea="Reverse a string.",
    budget_micros=500_000,
    rounds=(Round(1, 500_000, 2),),
    checks=(
        CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
        CheckSpec("c02", "empty string", "test_c02.py", "t1"),
    ),
    tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
    approved_by_investor=True,
)
GOOD = "def reverse(s):\n    return s[::-1]\n"


def scripted_worker(code, *, status="done", outcome=Outcome.COMPLETED, cost=12_345):
    calls = []

    def run_slice(spec, workspace, log_path, *, env):
        calls.append(spec)
        if code is not None:
            (workspace / "rev.py").write_text(code)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("{}\n")
        return SliceRun(
            outcome=outcome,
            usage=Usage(cost, 100, 20, 300),
            status={"status": status, "reason": "scripted"},
            session_id=str(spec.session_id),
            exit_code=0,
            duration_s=0.1,
            log_path=log_path,
        )

    run_slice.calls = calls
    return run_slice


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    (p.checks / "test_c01.py").write_text(C01)
    (p.checks / "test_c02.py").write_text(C02)
    return p


def approve(paths, ledger):
    ledger.append(
        Event(
            run="r1",
            round=0,
            actor="investor",
            event=EventType.APPROVED,
            data={"hashes": content_hashes(SHEET, paths.checks)},
        )
    )


def first_round(paths, worker, *, approved=True):
    with LedgerWriter(paths.ledger) as ledger:
        if approved:
            approve(paths, ledger)
        return run_first_round(SHEET, paths, ledger, "r1", env={"HOME": "/h"}, slice_runner=worker)


def test_correct_work_passes_every_check_and_unlocks(paths):
    worker = scripted_worker(GOOD)
    report = first_round(paths, worker)
    assert (report.passed, report.unlocked, report.outcome) == (2, True, Outcome.COMPLETED)
    kinds = [(e.actor, e.event) for e in read_events(paths.ledger)]
    assert kinds == [
        ("investor", EventType.APPROVED),
        ("boss", EventType.HIRED),
        ("worker:w1", EventType.SLICE_START),
        ("worker:w1", EventType.SLICE_END),
        ("gate", EventType.CHECK_RESULT),
        ("gate", EventType.CHECK_RESULT),
        ("boss", EventType.ROUND_CLOSED),
    ]
    assert total(read_events(paths.ledger)).cost_micros == 12_345


def test_wrong_work_does_not_unlock(paths):
    report = first_round(paths, scripted_worker("def reverse(s):\n    return s\n"))
    assert report.passed == 1  # the empty-string check passes by accident, the word check fails
    assert not report.unlocked
    closed = read_events(paths.ledger)[-1]
    assert closed.data == {"passed": 1, "total": 2, "unlocked": False}


def test_nothing_is_spawned_without_approval(paths):
    worker = scripted_worker(GOOD)
    with pytest.raises(NotApprovedError):
        first_round(paths, worker, approved=False)
    assert worker.calls == []


def test_a_check_edited_after_approval_blocks_the_round(paths):
    worker = scripted_worker(GOOD)
    with LedgerWriter(paths.ledger) as ledger:
        approve(paths, ledger)
        (paths.checks / "test_c01.py").write_text(C01.replace("'ba'", "'ab'"))
        with pytest.raises(NotApprovedError):
            run_first_round(SHEET, paths, ledger, "r1", env={}, slice_runner=worker)
    assert worker.calls == []


def test_slice_gets_80_percent_of_the_round_and_the_full_brief(paths):
    worker = scripted_worker(GOOD)
    first_round(paths, worker)
    [spec] = worker.calls
    assert spec.cap_micros == 400_000
    assert "Create rev.py with reverse(s)." in spec.prompt
    assert C01.rstrip() in spec.prompt and C02.rstrip() in spec.prompt
    assert spec.append_system_prompt.startswith("You are a builder")


def test_isolation_failure_is_recorded_and_stops_the_run(paths):
    def refuses(spec, workspace, log_path, *, env):
        raise IsolationError("2 hook event(s) ran")

    with pytest.raises(IsolationError):
        first_round(paths, refuses)
    events = read_events(paths.ledger)
    assert events[-2].event is EventType.ERROR and events[-2].cost_micros is None
    assert events[-1].event is EventType.STOPPED
    assert not any(e.event is EventType.CHECK_RESULT for e in events)


def test_blocked_worker_is_recorded(paths):
    first_round(paths, scripted_worker(None, status="blocked"))
    blocked = [e for e in read_events(paths.ledger) if e.event is EventType.BLOCKED]
    assert blocked[0].data == {"reason": "scripted"}


def test_unknown_cost_stays_unknown_in_the_ledger(paths):
    first_round(paths, scripted_worker(GOOD, cost=None, outcome=Outcome.CRASHED))
    slice_end = next(e for e in read_events(paths.ledger) if e.event is EventType.SLICE_END)
    assert slice_end.cost_micros is None
    assert slice_end.data["outcome"] == "crashed"
    assert total(read_events(paths.ledger)).unknown_cost_events == 1


def test_task_prompt_never_starts_with_a_dash(paths):
    assert not task_prompt(SHEET, paths).startswith("-")
