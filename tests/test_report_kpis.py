"""The KPIs section of `boss report`: figures from the ledger, "not recorded" where it is silent."""

from boss.ledger import Event, EventType
from boss.report import build_report, render_report


def ev(actor: str, event: EventType, ts: str = "2026-10-02T10:00:00+00:00", **fields) -> Event:
    data = fields.pop("data", {})
    return Event(run="r1", round=1, actor=actor, event=event, ts=ts, data=data, **fields)


def slice_end() -> Event:
    return ev("worker:w1", EventType.SLICE_END, data={"outcome": "completed", "status": {}})


def result(check: str, status: str, scope: str | None) -> Event:
    data = {"check": check, "status": status} | ({"scope": scope} if scope else {})
    return ev("gate", EventType.CHECK_RESULT, data=data)


def kpis(*events: Event) -> list[str]:
    text = render_report(build_report(list(events)))
    section = text.split("\nKPIs\n")[1].split("\n\n")[0]
    return [line.strip() for line in section.splitlines()]


APPROVED = ev("investor", EventType.APPROVED, data={"hashes": {}})
STARTED = ev("boss", EventType.STARTED, data={"config": {}})


def test_a_delivered_run_with_its_figures():
    lines = kpis(
        STARTED,
        ev("boss", EventType.BOSS_CALL, cost_micros=2_000),
        APPROVED,
        slice_end(),
        result("c1", "passed", "product"),
        result("c2", "passed", "product"),
        ev("boss", EventType.ROUND_CLOSED, ts="2026-10-02T10:02:05+00:00", data={}),
    )
    assert lines == [
        "Delivered: yes (2 of 2 checks pass on the product)",
        "False pass: not measured (the run had no checks its workers never saw)",
        "Cost: $0.0020 (estimated)",
        "Time: 2m05s from the first to the last ledger event, waiting for the investor included",
        "Investor questions: 1",
    ]


def test_every_visible_check_passing_but_a_held_out_check_failing_is_a_false_pass():
    lines = kpis(
        STARTED,
        APPROVED,
        slice_end(),
        result("c1", "passed", "product"),
        result("h1", "passed", "held_out"),
        result("h2", "failed", "held_out"),
    )
    assert "Held-out checks: 1 of 2 passed on the product" in lines
    assert "False pass: YES (every visible check passed, 1 of 2 held-out failed)" in lines


def test_a_run_whose_held_out_checks_all_passed_is_not_a_false_pass():
    lines = kpis(
        APPROVED, slice_end(), result("c1", "passed", "product"), result("h1", "passed", "held_out")
    )
    assert "False pass: no (every held-out check passed too)" in lines


def test_a_run_that_failed_a_visible_check_is_not_delivered_and_cannot_be_a_false_pass():
    lines = kpis(
        APPROVED,
        slice_end(),
        result("c1", "passed", "product"),
        result("c2", "failed", "product"),
        result("h1", "failed", "held_out"),
    )
    assert lines[0] == "Delivered: NO (1 of 2 checks pass on the product)"
    assert "False pass: no (the product did not pass every visible check)" in lines


def test_a_ledger_from_before_the_product_verdict_says_not_recorded_never_a_guess():
    lines = kpis(APPROVED, slice_end(), result("c1", "passed", None))
    assert lines[0] == "Delivered: not recorded (no verdict on the product in this ledger)"
    assert "False pass: not recorded" in lines


def test_a_run_that_never_built_anything_did_not_deliver():
    assert kpis(STARTED, APPROVED)[0] == "Delivered: NO (nothing was built)"


def test_a_single_event_has_no_time_and_unknown_cost_stays_beside_the_total():
    lines = kpis(ev("boss", EventType.BOSS_CALL, cost_micros=None))
    assert "Time: not recorded" in lines
    assert "Cost: $0.0000 + 1 event(s) of unknown cost (estimated)" in lines


def test_the_questions_are_those_of_the_rule():
    lines = kpis(
        APPROVED,
        ev("investor", EventType.RULED, data={"ruling": "dropped", "check": "c1"}),
        ev("boss", EventType.ABANDONED, data={"task": "t1", "reason": "disputed"}),
        ev("investor", EventType.STOPPED, data={"reason": "round 2 not funded"}),
    )
    assert lines[-1] == "Investor questions: 4"
