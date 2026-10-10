"""A dispute with nobody at a terminal to rule on it (Claude Code's Bash tool, a pipe): the run
stops with the dispute pending instead of setting the task aside, the investor rules with
`antstreet approve RUN --dispute CHECK --ruling drop|keep`, and `antstreet resume` carries on from
the
ruling. Scripted workers and the real gate; no model calls."""

import io
import sys

import pytest
from test_dispute_wrong_check import C05_IS_WRONG, CHECKS, CORRECT, SHEET, live_run, vowels
from test_firm import Script, dispute, events_of, run

from antstreet import rulings
from antstreet.cli import (
    EXIT_AWAITING,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    _finish,
    _unattended,
    main,
)
from antstreet.firm import FirmReport
from antstreet.ledger import Event, EventType, LedgerWriter, read_events
from antstreet.rulings import RULING_AWAITED, awaited
from antstreet.rundir import RunPaths
from antstreet.signing import SIG_KEY
from antstreet.termsheet import TermSheet

DESCRIBED = "Text with special characters and numbers ignores non-vowels"
# Satisfies the wrong c05 as the investor's "keep" demands: "0" counts.
CORRECT_FOR_C05 = 'def count_vowels(text):\n    return sum(1 for c in text if c in "aeiouAEIOU0")\n'


def disputing_worker(*then):
    disputes = [dispute("c05", C05_IS_WRONG)]
    return Script(vowels(CORRECT, "done"), vowels(CORRECT, disputes=disputes), *then)


def test_unattended_dispute_stops_the_run_pending_instead_of_setting_the_task_aside(tmp_path):
    paths, sheet = live_run(tmp_path)
    report, said = run(paths, disputing_worker(), sheet, unattended=True)
    assert events_of(paths, EventType.ABANDONED) == []
    assert events_of(paths, EventType.RULED) == []
    [stop] = events_of(paths, EventType.STOPPED)
    assert stop.actor == "boss" and stop.data["disputes"] == [
        {"task": "count_vowels", "check": "c05", "worker": "w1"}
    ]
    assert report.stopped == RULING_AWAITED and not report.all_passed
    assert f'Task count_vowels: w1 disputes check c05 ({DESCRIBED}): "{C05_IS_WRONG}"' in said
    assert not any("[d]rop the check" in line for line in said)  # nobody was asked
    assert awaited(read_events(paths.ledger)) == stop.data["disputes"]


def resume(paths, ruling=None):
    """What `antstreet approve --dispute` and `antstreet resume` append, as the investor."""
    with LedgerWriter(paths.ledger) as ledger:
        if ruling:
            data = {"task": "count_vowels", "worker": "w1", "check": "c05", "ruling": ruling}
            ledger.append(
                Event(run="r1", round=1, actor="investor", event=EventType.RULED, data=data)
            )
        ledger.append(Event(run="r1", round=1, actor="investor", event=EventType.RESUMED))


def test_a_dropped_dispute_lets_resume_finish_the_task_without_the_check(tmp_path):
    paths, sheet = live_run(tmp_path)
    worker = disputing_worker()
    run(paths, worker, sheet, unattended=True)
    resume(paths, rulings.DROPPED)
    report, _ = run(paths, worker, sheet, unattended=True)
    assert report.all_passed and (report.passed, report.total) == (6, 6)
    assert len(worker.specs) == 2  # no slice was needed: the ruling settled it
    assert events_of(paths, EventType.ABANDONED) == []
    assert (paths.product / "vowels.py").read_text() == CORRECT


def test_a_kept_dispute_makes_resume_fund_the_worker_again_to_satisfy_the_check(tmp_path):
    paths, sheet = live_run(tmp_path)
    worker = disputing_worker(vowels(CORRECT_FOR_C05, "done"))
    run(paths, worker, sheet, unattended=True)
    resume(paths, rulings.KEPT)
    report, _ = run(paths, worker, sheet, unattended=True)
    assert report.all_passed and (report.passed, report.total) == (7, 7)
    assert len(worker.specs) == 3
    assert "check c05 stands. Make it pass." in worker.specs[2].prompt
    assert events_of(paths, EventType.ABANDONED) == []


def test_resume_with_no_ruling_stops_again_and_asks_nobody(tmp_path):
    paths, sheet = live_run(tmp_path)
    worker = disputing_worker()
    run(paths, worker, sheet, unattended=True)
    resume(paths)
    report, _ = run(paths, worker, sheet, unattended=True)
    assert report.stopped == RULING_AWAITED and len(worker.specs) == 2
    assert len(events_of(paths, EventType.STOPPED)) == 2
    assert awaited(read_events(paths.ledger))[0]["check"] == "c05"


def test_with_a_terminal_the_dispute_is_still_asked_there(tmp_path):
    paths, sheet = live_run(tmp_path)
    report, said = run(paths, disputing_worker(), sheet, answers=["d"])
    assert any("[d]rop the check" in line for line in said)
    assert [e.data["ruling"] for e in events_of(paths, EventType.RULED)] == ["dropped"]
    assert events_of(paths, EventType.STOPPED) == [] and report.all_passed


@pytest.fixture
def project_run(tmp_path):
    """A run where `boss` keeps them, .boss/runs/r1 of a project, stopped on the c05 dispute."""
    project = tmp_path / "project"
    paths = RunPaths(project / ".boss" / "runs" / "r1")
    paths.checks.mkdir(parents=True)
    for name, code in CHECKS.items():
        (paths.checks / name).write_text(code)
    run(paths, disputing_worker(), TermSheet.from_json(SHEET.read_text()), unattended=True)
    return project, paths


def cli(project, *argv):
    said = []
    code = main([*argv, "--dir", str(project)], say=said.append, environ={"HOME": "/nonexistent"})
    return code, "\n".join(said)


def test_approve_dispute_records_the_signed_ruling_once(project_run):
    project, paths = project_run
    code, said = cli(project, "approve", "r1", "--dispute", "c05", "--ruling", "drop")
    assert code == EXIT_OK and "antstreet resume r1" in said
    [ruled] = events_of(paths, EventType.RULED)
    assert ruled.actor == "investor" and SIG_KEY in ruled.data
    assert {k: ruled.data[k] for k in ("task", "worker", "check", "ruling")} == {
        "task": "count_vowels", "worker": "w1", "check": "c05", "ruling": "dropped"
    }  # fmt: skip
    assert awaited(paths.events()) == []
    code, said = cli(project, "approve", "r1", "--dispute", "c05", "--ruling", "keep")
    assert code == EXIT_FAILED and "not waiting for a ruling on 'c05'" in said
    assert len(events_of(paths, EventType.RULED)) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ("--dispute", "c01", "--ruling", "drop"),  # not disputed
        ("--dispute", "c05"),  # no ruling
        ("--ruling", "drop"),  # no check
        ("--dispute", "c05", "--ruling", "drop", "--sheet", "0123456789abcdef"),
    ],
)
def test_approve_dispute_refuses_anything_but_one_waiting_check_and_a_ruling(project_run, argv):
    project, paths = project_run
    before = paths.ledger.read_bytes()
    code, _ = cli(project, "approve", "r1", *argv)
    assert code in (EXIT_FAILED, EXIT_USAGE)
    assert paths.ledger.read_bytes() == before


def test_a_run_resumed_after_a_cli_ruling_finishes(project_run):
    project, paths = project_run
    cli(project, "approve", "r1", "--dispute", "c05", "--ruling", "drop")
    with paths.writer() as ledger:
        ledger.append(Event(run="r1", round=1, actor="investor", event=EventType.RESUMED))
    report, _ = run(paths, Script(), TermSheet.from_json(SHEET.read_text()), unattended=True)
    assert report.all_passed and (report.passed, report.total) == (6, 6)


def test_only_the_real_input_on_a_stdin_that_is_no_terminal_is_unattended(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO())  # StringIO.isatty() is False
    assert _unattended(input) and not _unattended(lambda q: "k")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert not _unattended(input)


def test_finish_exits_awaiting_and_prints_the_commands_last(project_run):
    _, paths = project_run
    said = []
    assert _finish(paths, FirmReport(6, 7, RULING_AWAITED), said.append) == EXIT_AWAITING
    tail = "\n".join(said[-2:])
    assert "antstreet approve r1 --dispute c05 --ruling drop" in tail
    assert "antstreet approve r1 --dispute c05 --ruling keep" in tail
    assert "antstreet resume r1" in tail and "the ruling is yours, never the agent's" in tail


def _event(actor, kind, **data):
    return Event(run="r1", round=1, actor=actor, event=kind, data=data)


def _waits(task, check):
    disputes = [{"task": task, "check": check, "worker": "w1"}]
    return _event("boss", EventType.STOPPED, reason=RULING_AWAITED, disputes=disputes)


def test_awaited_keeps_every_stop_since_the_resume_and_drops_what_was_ruled():
    a, b = _waits("t1", "c01"), _waits("t2", "c04")  # two parallel tasks stopped in one wave
    limit = _event("rule", EventType.STOPPED, reason="spend limit")
    assert [d["check"] for d in awaited([a, b, limit])] == ["c01", "c04"]
    kept = _event("investor", EventType.RULED, task="t1", check="c01", ruling=rulings.KEPT)
    assert [d["check"] for d in awaited([a, b, kept])] == ["c04"]
    assert awaited([a, b, _event("investor", EventType.RESUMED)]) == []
    forged = _event(
        "worker:w1", EventType.STOPPED, reason=RULING_AWAITED, disputes=[{"check": "c09"}]
    )
    assert awaited([forged]) == []  # only the boss puts a dispute up for a ruling
    assert awaited([]) == []  # an older ledger has no such stop: nothing waits
