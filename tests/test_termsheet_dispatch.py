"""The term sheet under --dispatch: what the investor reads, what an edit can and cannot do, and
that an edit made after approval voids it."""

import random

import pytest

from boss.approval import (
    NotApprovedError,
    content_hashes,
    render,
    require_approval,
    review_term_sheet,
)
from boss.dispatch import DispatchPolicy, DispatchView, RunLevel, plan_cascade, plan_dispatch
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.termsheet import CheckSpec, Round, Task, TermSheet, TermSheetError, validate

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
POLICY = DispatchPolicy("sonnet", 100_000)
VIEW = DispatchView(POLICY, RunLevel("haiku", "off", 0, 1), 2, {})
BASE = TermSheet(
    "Reverse a string.",
    800_000,
    (Round(1, 800_000, 1),),
    (CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
    (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
)
SHEET = plan_dispatch(BASE, tier="haiku", profile=None, policy=POLICY, reads={})


@pytest.fixture
def run(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(C01)
    ledger_path = tmp_path / "ledger.jsonl"

    def review(answers, edits=None, view=VIEW, sheet=SHEET):
        said, calls = [], []

        def ask(prompt):
            index = len(calls)
            calls.append(prompt)
            if edits and index in edits:
                edits[index]()
            return answers[index]

        with LedgerWriter(ledger_path) as ledger:
            result = review_term_sheet(
                sheet, checks, tmp_path, ledger, "r1", ask=ask, say=said.append, view=view
            )
        return result, "\n".join(said)

    review.checks, review.dir = checks, tmp_path
    review.events = lambda: read_events(ledger_path)
    review.edit = lambda old, new: (tmp_path / "term_sheet.json").write_text(
        (tmp_path / "term_sheet.json").read_text().replace(old, new)
    )
    return review


def test_the_table_sits_after_the_tasks_and_before_the_checks(run):
    _, said = run(["r"])
    assert said.index("Task t1") < said.index("Route: one agent") < said.index("DISPATCH")
    assert said.index("Worst case if every task steps up") < said.index("Check c01")
    assert "t1    builder  haiku  default  sonnet, once" in said


def test_nothing_is_shown_without_dispatch(run):
    _, said = run(["r"], view=None, sheet=BASE)
    assert "DISPATCH" not in said and "Route:" not in said
    assert render(BASE, run.checks) == render(BASE, run.checks, None, None)


def test_approval_records_the_route_and_the_saved_sheet_carries_the_dispatch(run):
    approved, _ = run(["a"])
    assert approved is not None and approved.route == "one_agent"
    [event] = run.events()
    assert event.data["route"] == "one_agent"
    assert event.data["hashes"] == content_hashes(approved, run.checks)
    saved = TermSheet.from_json((run.dir / "term_sheet.json").read_text())
    assert saved.tasks[0].dispatch == SHEET.tasks[0].dispatch and saved.approved_by_investor


def test_under_the_cascade_the_approval_records_the_routers_start_and_its_reason(run):
    cascade = DispatchPolicy("opus", 100_000, cascade=True)
    sheet = plan_cascade(BASE, starts={"t1": "haiku"}, profile=None, policy=cascade, reads={})
    start = {"tier": "haiku", "effort": "off", "kind": "files=1 checks=1-2", "source": "prior"}
    start |= {"why": "cold start, ...", "features": {"idea_chars": 17, "checks": 1}}
    shown = DispatchView(cascade, RunLevel("haiku", "off", 0, 1), 2, {}, {"t1": start})
    approved, said = run(["a"], view=shown, sheet=sheet)
    assert approved is not None and "Router's start for t1: haiku/off, cold start, ..." in said
    [event] = run.events()
    assert event.data["routed"] == {"t1": start}  # signed with the approval, as shown


def test_the_rules_route_records_no_router_start(run):
    run(["a"])
    [event] = run.events()
    assert "routed" not in event.data


def test_without_dispatch_the_approval_event_is_what_it_always_was(run):
    approved, _ = run(["a"], view=None, sheet=BASE)
    assert approved is not None
    [event] = run.events()
    assert set(event.data) == {"hashes"}


def test_an_edit_that_routes_to_a_model_over_the_ceiling_cannot_be_approved(run):
    approved, said = run(
        ["e", "", "", "a"],  # edit, Enter, Enter again after the refusal, approve
        edits={
            1: lambda: run.edit('"tier": "haiku"', '"tier": "opus"'),
            2: lambda: run.edit('"tier": "opus"', '"tier": "haiku"'),
        },
    )
    assert "tier 'opus' is not one of ['haiku', 'sonnet']" in said
    assert approved is not None and approved.tasks[0].dispatch.tier == "haiku"


def test_an_edit_made_without_choosing_edit_is_caught_when_it_changes_what_was_shown(run):
    approved, said = run(
        ["a", "r"], edits={0: lambda: run.edit('"effort": "default"', '"effort": "high"')}
    )
    assert approved is None
    assert "changed since it was shown" in said
    assert run.events()[-1].event is EventType.STOPPED


def test_the_investor_may_force_the_firm_route_and_the_table_shows_it(run):
    approved, said = run(
        ["e", "", "a"], edits={1: lambda: run.edit('"route": "one_agent"', '"route": "firm"')}
    )
    assert approved is not None and approved.route == "firm"
    assert "Route: firm (1 task, files rev.py)" in said
    assert run.events()[0].data["route"] == "firm"


def test_a_sheet_with_dispatch_cannot_be_approved_when_dispatch_is_off(run):
    approved, said = run(["a", "r"], view=None)
    assert approved is None
    assert "carries dispatch, but --dispatch is off" in said


def test_validate_refuses_dispatch_with_the_flag_off_and_a_missing_one_with_it_on(tmp_path):
    (tmp_path / "test_c01.py").write_text(C01)
    with pytest.raises(TermSheetError, match="--dispatch is off"):
        validate(SHEET, tmp_path)
    with pytest.raises(TermSheetError, match="has no dispatch"):
        validate(BASE, tmp_path, POLICY)
    validate(SHEET, tmp_path, POLICY)


def test_changing_any_byte_of_the_dispatch_after_approval_voids_it(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(C01)
    approved = SHEET
    event = Event(
        run="r", round=0, actor="investor", event=EventType.APPROVED,
        data={"hashes": content_hashes(approved, checks), "route": approved.route},
    )  # fmt: skip
    require_approval([event], approved, checks)
    text = approved.to_json()
    start = text.index('"dispatch"')
    rng = random.Random(4801)
    flipped = loaded_ok = 0
    for _ in range(600):
        at, bit = rng.randrange(start, len(text)), 1 << rng.randrange(7)
        mutated = text[:at] + chr(ord(text[at]) ^ bit) + text[at + 1 :]
        try:
            loaded = TermSheet.from_json(mutated)
        except (TermSheetError, ValueError):
            flipped += 1  # no longer a term sheet: nothing to approve
            continue
        if loaded.to_json() == text:
            continue
        loaded_ok += 1
        with pytest.raises(NotApprovedError):
            require_approval([event], loaded, checks)
    assert flipped and loaded_ok  # the run reached both outcomes
