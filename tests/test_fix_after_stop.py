"""`fund --fix-after-stop`: the critic's fix round offered on a run that ended only because a
round closed below its unlock threshold. The fix money is the investor's top-up of that round,
which reopens it. The same fake `claude` as test_pipeline.py; no model call is made."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_pipeline import (
    CLAIM,
    EXAMINED,
    GOOD,
    Fx,
    approvals,
    asked,
    finding,
    ok,
    product_verdicts,
)

from boss import budget, signing
from boss.cli import EXIT_INCOMPLETE, EXIT_INTERRUPTED, EXIT_OK, EXIT_USAGE
from boss.firm import FirmReport, locked_stop
from boss.ledger import Event, EventType, read_events
from boss.pipeline import Pipeline, Setup, recorded_setup
from boss.termsheet import TermSheet

BAD = {"files": {"rev.py": "def reverse(s):\n    return s\n"}}
# --budget 0.12 --slice 0.005: three bad slices (w1 twice, fired, then w2) and round 1 cannot fund
# a fourth, so it closes 0/1, locked. A fourth slice, if one is funded, fixes the product.
EARLY = ("--roles", "critic", "--budget", "0.12", "--slice", "0.005")
LOCKED = locked_stop(1)
TOP_UP_QUESTION = "Add these 1 checks and top up round 1 by $0.11? [y]es / [n]o "


@pytest.fixture
def fx(tmp_path):
    return Fx(tmp_path)


def locked_then_fixed(fx, *, fixes: bool = True) -> None:
    fx.set("worker", [BAD, BAD, BAD, {"files": {"rev.py": GOOD}} if fixes else BAD])
    fx.set("critic", ok({"findings": [finding()]}))


def sheet_of(fx) -> TermSheet:
    return TermSheet.from_json((fx.run_dir / "term_sheet.json").read_text())


def test_a_locked_round_is_reopened_by_the_investors_top_up_and_the_worker_fixes_it(fx):
    locked_then_fixed(fx)
    out = fx.fund(*EARLY, "--fix-after-stop")
    assert out.code == EXIT_OK and f"Critic verified a finding (high): {CLAIM}" in out.text
    shown = out.index("say", "Round 1 closed below its unlock threshold, so the run ended there")
    assert out.index("say", "Check c02 [t1]") < shown < out.index("ask", TOP_UP_QUESTION)
    assert asked(out, "Add these") == [TOP_UP_QUESTION]
    assert "no fix round is offered" not in out.text
    # signed approval of the amended sheet, then the money as the investor's top-up of round 1
    _, amendment = approvals(fx)
    assert (amendment.actor, amendment.round) == ("investor", 1)
    assert amendment.data["round"] == 1 and amendment.data["added_checks"] == ["c02"]
    [top_up] = fx.events(EventType.TOPPED_UP)
    assert (top_up.actor, top_up.round, top_up.data["micros"]) == ("investor", 1, 110_000)
    assert top_up.data["sig"].startswith("v2:")
    events = fx.events()
    assert events.index(amendment) < events.index(top_up)
    assert fx.events(EventType.RULED) == []  # answered by the yes: nothing declined
    # no round is added; the sheet's budget is what was approved, the top-up is on the ledger
    sheet = sheet_of(fx)
    assert [(r.n, r.budget_micros, r.unlock_checks) for r in sheet.rounds] == [(1, 120_000, 2)]
    assert sheet.budget_micros == 120_000 and [c.id for c in sheet.checks] == ["c01", "c02"]
    # the round reopened, a worker was told of the new check and fixed the product
    assert fx.calls() == ["boss", "worker", "worker", "worker", "critic", "worker"]
    assert "--- check c02" in (fx.folder / "last_worker.txt").read_text()
    assert product_verdicts(fx) == {"c01": "passed", "c02": "passed"}
    closed = [e.data["unlocked"] for e in fx.events(EventType.ROUND_CLOSED)]
    assert closed == [False, True] and fx.events(EventType.SLICE_END)[-1].round == 1


def test_with_held_out_checks_the_top_up_approval_covers_them_and_the_worker_runs(fx):
    """The firm checks the approval against the held-out folder before every slice: an amendment
    approved without its hashes would leave the top-up paid for and no worker allowed to run."""
    costly = BAD | {"cost": 0.051}  # round 1 has room for the examiner's cap and 3 such slices
    fx.set("worker", [costly, costly, costly, {"files": {"rev.py": GOOD}}])
    fx.set("critic", ok({"findings": [finding()]}))
    fx.set("examiner", ok(EXAMINED))
    out = fx.fund(
        "--roles", "critic", "--budget", "0.26", "--slice", "0.06", "--fix-after-stop",
        "--held-out", "1",
    )  # fmt: skip
    assert "Held-out check h01" in out.text and len(asked(out, "Add these")) == 1
    first, amendment = approvals(fx)
    assert amendment.data["held_out_hashes"] == first.data["held_out_hashes"] != {}
    assert out.code == EXIT_OK and fx.calls().count("worker") == 4
    assert product_verdicts(fx) == {"c01": "passed", "c02": "passed"}


def test_a_finding_whose_task_was_set_aside_is_not_offered_so_nothing_is_topped_up(fx):
    """A task set aside stays set aside: a top-up for its checks would reopen a round with no
    task to work on, so the round would close again with the investor's yes spent on nothing."""
    fx.set("worker", BAD | {"status": "blocked", "reason": "stuck"})
    fx.set("critic", ok({"findings": [finding()]}))
    out = fx.fund("--roles", "critic", "--fix-after-stop", answers={"Task": "s"})
    assert out.code == EXIT_INCOMPLETE and f"Critic verified a finding (high): {CLAIM}" in out.text
    assert "its task t1 was set aside" in out.text and asked(out, "Add these") == []
    assert fx.events(EventType.TOPPED_UP) == [] and len(approvals(fx)) == 1
    [ruling] = fx.events(EventType.RULED)
    assert ruling.actor == "investor" and ruling.data["ruling"] == "declined"
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]


def test_the_reopened_round_never_spends_past_its_budget_and_the_top_up(fx):
    locked_then_fixed(fx, fixes=False)  # the fix never lands: the round spends all it may
    out = fx.fund(*EARLY, "--fix-after-stop", "--no-firing")
    assert out.code == EXIT_INCOMPLETE and f"Ended early: {LOCKED}" in out.text
    events, sheet = fx.events(), sheet_of(fx)
    funded = budget.round_budget(sheet, events, 1)
    assert funded == 120_000 + 110_000  # the sheet's round plus the investor's top-up, no more
    spent = budget.round_spend(events, 1).cost_micros
    assert spent <= funded - 100_000  # every slice cap left the reserve unspent
    # every slice was capped inside what the round had left, reserve held back
    starts = [e for e in events if e.event is EventType.SLICE_START]
    assert all(e.data["cap_micros"] <= 5_000 for e in starts)
    assert fx.calls().count("critic") == 1  # one review cycle: the second lock offers nothing
    assert len(fx.events(EventType.TOPPED_UP)) == 1


def test_the_ledger_of_a_reopened_round_verifies(fx):
    locked_then_fixed(fx)
    assert fx.fund(*EARLY, "--fix-after-stop").code == EXIT_OK
    key = signing.load_key(fx.project / ".boss" / signing.KEY_FILE)
    signed = [e for e in read_events(fx.run_dir / "ledger.jsonl") if e.actor == "investor"]
    assert len(signed) == 3 and all(signing.verify(key, e) for e in signed)


def test_without_the_flag_a_locked_round_still_offers_no_fix_round(fx):
    locked_then_fixed(fx)
    out = fx.fund(*EARLY)
    assert out.code == EXIT_INCOMPLETE and asked(out, "Add these") == []
    assert f"The run ended early ({LOCKED}): no fix round is offered." in out.text
    [ruling] = fx.events(EventType.RULED)
    assert ruling.actor == "investor" and ruling.data["ruling"] == "declined"
    assert fx.events(EventType.TOPPED_UP) == [] and len(approvals(fx)) == 1
    started = fx.events(EventType.STARTED)[0].data["roles"]
    assert "fix_after_stop" not in started  # off leaves the started event as it always was


def test_a_no_to_the_top_up_spends_nothing_and_the_round_stays_locked(fx):
    locked_then_fixed(fx)
    out = fx.fund(*EARLY, "--fix-after-stop", answers={"Add these": "n"})
    assert out.code == EXIT_INCOMPLETE and "No fix round." in out.text
    assert fx.events(EventType.TOPPED_UP) == [] and len(approvals(fx)) == 1
    assert sheet_of(fx).budget_micros == 120_000 and len(sheet_of(fx).checks) == 1
    [ruling] = fx.events(EventType.RULED)
    assert ruling.actor == "investor" and ruling.data["ruling"] == "declined"


def test_with_no_one_at_the_terminal_nothing_is_funded_without_an_answer(fx):
    """No TTY: input ends at the question. As for any fix round, that is no approval: it
    is recorded as declined, and no money or check is added."""
    locked_then_fixed(fx)
    out = fx.fund(*EARLY, "--fix-after-stop", answers={"Add these": EOFError})
    assert out.code == EXIT_INCOMPLETE and fx.events(EventType.TOPPED_UP) == []
    assert len(approvals(fx)) == 1 and fx.calls().count("worker") == 3
    [ruling] = fx.events(EventType.RULED)
    assert ruling.actor == "investor" and ruling.data["ruling"] == "declined"
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]


def test_the_flag_needs_the_critic(fx):
    out = fx.fund("--fix-after-stop")
    assert out.code == EXIT_USAGE and "--fix-after-stop needs --roles critic" in out.text
    assert fx.calls() == []


def test_a_ctrl_c_at_the_question_is_offered_again_on_resume_with_the_flag_from_the_ledger(fx):
    locked_then_fixed(fx)
    out = fx.fund(*EARLY, "--fix-after-stop", answers={"Add these": KeyboardInterrupt})
    assert out.code == EXIT_INTERRUPTED and fx.events(EventType.TOPPED_UP) == []
    assert recorded_setup(fx.events()) == Setup(("critic",), "haiku", None, True)
    out = fx.run("resume")
    assert out.code == EXIT_OK and asked(out, "Add these") == [TOP_UP_QUESTION]
    assert product_verdicts(fx) == {"c01": "passed", "c02": "passed"}


@pytest.mark.sigint
def test_a_fix_interrupted_mid_slice_continues_on_resume_without_a_second_question(fx):
    locked_then_fixed(fx)
    (fx.folder / "interrupt").write_text("3")  # the fourth worker slice: the fix
    out = fx.fund(*EARLY, "--fix-after-stop")
    assert out.code == EXIT_INTERRUPTED and len(fx.events(EventType.TOPPED_UP)) == 1
    (fx.folder / "interrupt").unlink()
    out = fx.run("resume")
    assert out.code == EXIT_OK and asked(out, "Add these") == []
    assert fx.calls() == ["boss", "worker", "worker", "worker", "critic", "worker"]
    assert product_verdicts(fx) == {"c01": "passed", "c02": "passed"}
    assert len(fx.events(EventType.TOPPED_UP)) == 1  # the top-up is never paid twice
    before = fx.events()
    assert fx.run("resume").code == EXIT_OK and fx.events() == before


class _Paths:
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    def events(self) -> list[Event]:
        return self._events


def _reopenable(stopped: str | None, *later: Event, flag: bool = True) -> int | None:
    events = [
        Event("r", 1, "boss", EventType.ROUND_CLOSED, data={"passed": 0, "total": 1}),
        *later,
    ]
    setup = Setup(("critic",), "haiku", None, flag)
    pipe = Pipeline(setup, Path("."), _Paths(events), None, "r", {}, "", input, print)  # type: ignore[arg-type]
    sheet = TermSheet.from_json(json.dumps(_SHEET))
    return pipe._reopenable(sheet, FirmReport(0, 1, stopped))


_SHEET = {
    "idea": "x",
    "budget_micros": 120_000,
    "rounds": [{"n": 1, "budget_micros": 120_000, "unlock_checks": 1}],
    "tasks": [{"id": "t1", "brief": "b", "paths": ["rev.py"]}],
    "checks": [{"id": "c01", "description": "d", "task": "t1", "file": "test_c01.py"}],
    "approved_by_investor": True,
}


def test_only_a_stop_at_a_locked_round_is_reopenable():
    assert _reopenable(LOCKED) == 1
    assert _reopenable(LOCKED, flag=False) is None
    assert _reopenable(None) is None
    ceiling = "stopped: spend $1 is over the run ceiling of $0.5"
    for other in (ceiling, "paused: plan", "awaiting the investor's ruling on a dispute"):
        assert _reopenable(other) is None
    stop = Event("r", 1, "rule", EventType.STOPPED, data={"reason": "a hard limit"})
    assert _reopenable("stopped earlier", stop) is None
    assert _reopenable(LOCKED, stop) is None  # a stop on the ledger is never lifted by this
    top_up = Event("r", 1, "investor", EventType.TOPPED_UP, data={"micros": 1})
    assert _reopenable(LOCKED, top_up) is None  # no longer locked: nothing to reopen
