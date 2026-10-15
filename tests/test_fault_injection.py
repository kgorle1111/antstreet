"""Does `resume` recover with zero double-spend? (U1)

Every fault in `fault_support` is injected into a real `antstreet fund` (its own process, a fake
`claude`, the real gate, a signed ledger), then `antstreet resume` runs until the run ends, once
more after that, and `antstreet verify` checks the ledger. Each trial must either deliver or stop
with a reason that names the next command, and never pay for a slice twice or lose a cost unseen.
The measured table in docs/RECOVERY.md is regenerated here and must match.
"""

import re

import pytest
from docs_support import DOCS, read
from fault_support import (
    BASELINE_LINES,
    POINTS,
    ROWS,
    WORKER_FAULTS,
    all_trials,
    double_spends,
    summary,
    table,
)

from antstreet.cli import EXIT_INTERRUPTED, EXIT_OK
from antstreet.firm import INTERRUPTED_SLICE, STOPPED_PGID
from antstreet.ledger import Event, EventType

# The trials share one fixture (about 30 runs, threaded); under xdist they stay on one worker.
pytestmark = pytest.mark.xdist_group("fault-injection")


@pytest.fixture(scope="module")
def trials(tmp_path_factory):
    return all_trials(tmp_path_factory.mktemp("faults"))


def named(trials, fault, point=None):
    return [t for t in trials if t.fault == fault and point in (None, t.point)]


def test_every_fault_was_injected_at_every_point(trials):
    assert {(t.fault, t.point) for t in trials} >= {(k, p) for k in WORKER_FAULTS for p in POINTS}
    assert sorted(t.point for t in named(trials, "anchor_crash")) == list(
        range(1, BASELINE_LINES + 1)
    )
    [clean] = named(trials, "none")
    assert clean.recovered and len(clean.events) == BASELINE_LINES  # the sweep covers every line
    assert clean.billed_micros == clean.booked_micros == 24_000


def test_no_fault_pays_for_a_slice_twice(trials):
    assert {(t.fault, t.point): t.double_spends for t in trials if t.double_spends} == {}
    for t in trials:
        assert t.booked_micros <= t.billed_micros, (t.fault, t.point)


def test_a_crash_between_two_ledger_lines_never_buys_an_extra_slice(trials):
    [clean] = named(trials, "none")
    extra = {
        t.point: t.billed_micros - clean.billed_micros
        for t in named(trials, "anchor_crash")
        if t.recovered
    }
    assert extra == dict.fromkeys(range(3, BASELINE_LINES + 1), 0)


def test_the_double_spend_count_sees_each_way_to_pay_twice():
    def ev(kind, slice_n=1, cost=0, **data):
        return Event(run="r", round=1, actor="worker:w1", event=kind, cost_micros=cost,
                     data={"slice": slice_n, **data})  # fmt: skip

    start, gated = ev(EventType.SLICE_START), Event(
        run="r", round=1, actor="gate", event=EventType.CHECK_RESULT,
        data={"check": "c01", "status": "failed", "worker": "w1", "slice": 1},
    )  # fmt: skip
    end = ev(EventType.SLICE_END, cost=10, outcome="completed")
    assert double_spends([start, end, gated], 10) == 0
    assert double_spends([start, end, gated, end], 20) == 1  # booked twice
    assert double_spends([start, end, gated, start], 10) == 1  # run again after its end
    assert double_spends([start, end, ev(EventType.SLICE_START, 2)], 10) == 1  # never judged
    assert double_spends([start, end, gated], 9) == 1  # more booked than billed
    lost = ev(EventType.SLICE_END, cost=None, outcome="login")  # no work: nothing to judge
    assert double_spends([start, lost, ev(EventType.SLICE_START, 2)], 0) == 0


def test_every_trial_delivers_or_stops_saying_what_to_do(trials):
    stuck = [
        (t.fault, t.point, t.final.output[-300:])
        for t in trials
        if not (t.recovered or t.escalated)
    ]
    assert stuck == []


def test_no_spend_is_lost_unseen(trials):
    # Billed money that is on no ledger line is allowed only next to an event of unknown cost,
    # so the report's total reads as a lower bound (R7).
    assert {(t.fault, t.point): t.silent_loss_micros for t in trials if t.silent_loss_micros} == {}


def test_every_ledger_verifies_and_one_more_resume_changes_nothing(trials):
    assert [(t.fault, t.point) for t in trials if not t.verified] == []
    assert [(t.fault, t.point) for t in trials if t.rerun_changed] == []


def test_worker_faults_are_absorbed_without_a_resume(trials):
    for kind in ("kill_worker", "hang", "gibberish", "garbled_result"):
        for t in named(trials, kind):
            assert t.steps[0].command == "fund" and t.steps[0].code == EXIT_OK, (kind, t.point)


def test_a_killed_antstreet_books_the_slice_it_lost(trials):
    for t in named(trials, "kill_antstreet"):
        assert t.steps[0].code < 0  # really killed
        lost = [e for e in t.events if e.event is EventType.ERROR and INTERRUPTED_SLICE in e.data]
        assert [(e.actor, e.data[INTERRUPTED_SLICE], e.cost_micros) for e in lost] == [
            ("worker:w1", t.point, None)
        ]


def test_a_worker_left_running_by_a_killed_antstreet_is_stopped_before_the_slice_runs_again(
    trials,
):
    # `start_new_session` keeps the worker out of reach of a SIGKILL of `antstreet`; resume must
    # stop it before booking its slice and hiring again, or two agents write one workspace.
    for t in named(trials, "orphan_worker"):
        assert t.steps[0].code < 0 and t.recovered, t.point
        assert t.problems == (), t.problems  # no call ran beside it, and it is not left running
        [lost] = [e for e in t.events if e.event is EventType.ERROR and INTERRUPTED_SLICE in e.data]
        assert lost.data[INTERRUPTED_SLICE] == t.point
        assert isinstance(lost.data[STOPPED_PGID], int)


def test_ctrl_c_mid_slice_loses_the_cost_the_cli_reported(trials):
    # Known gap, measured: the runner reads the CLI's final result after Ctrl-C, but the
    # KeyboardInterrupt is raised before the slice is booked, so a known cost becomes unknown.
    # In a new session (call 1) it stays off the books; in a resumed one (call 2) the next slice's
    # cumulative session total books it.
    unbooked = {t.point: t.billed_micros - t.booked_micros for t in named(trials, "ctrl_c")}
    assert unbooked == {1: 10_000, 2: 0}
    for t in named(trials, "ctrl_c"):
        assert t.steps[0].code == EXIT_INTERRUPTED and t.recovered and t.unknown_events == 1


def test_a_second_resume_while_one_runs_is_refused_and_changes_nothing(trials):
    [t] = named(trials, "concurrent_resume")
    assert t.problems == () and t.recovered


def test_the_recovery_document_holds_the_measured_table(trials):
    text = read(DOCS / "RECOVERY.md")
    found = re.search(r"^\| Fault \|.*?(?=\n\n|\Z)", text, re.M | re.S)
    assert found, "docs/RECOVERY.md has no table starting with `| Fault |`"
    assert found.group(0).strip() == table(trials)
    assert len(ROWS) == len(found.group(0).strip().splitlines()) - 2
    assert summary(trials) in " ".join(text.split())
