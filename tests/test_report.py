import pytest

from boss.ledger import Billing, Event, EventType, total, totals_by
from boss.report import build_report, dollars, render_report


def ev(actor, event, round=1, **fields) -> Event:
    return Event(run="r1", round=round, actor=actor, event=event, **fields)


def check(check_id, status, detail="") -> Event:
    return ev(
        "gate", EventType.CHECK_RESULT, data={"check": check_id, "status": status, "detail": detail}
    )


def slice_end(worker, cost, outcome="completed", status="done", **tokens) -> Event:
    return ev(
        f"worker:{worker}",
        EventType.SLICE_END,
        cost_micros=cost,
        billing=Billing.SUBSCRIPTION,
        data={"outcome": outcome, "status": {"status": status, "reason": "because"}},
        **tokens,
    )


EVENTS = [
    ev("boss", EventType.BOSS_CALL, round=0, cost_micros=48_300, tokens_in=1200, tokens_out=900),
    ev("investor", EventType.APPROVED, round=0, data={"hashes": {}}),
    ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "model": "haiku"}),
    slice_end("w1", 5_896, tokens_in=1350, tokens_out=428, tokens_cached=10_738),
    check("c01", "failed", "pytest exited 1"),
    check("c02", "passed", "1 passed"),
    slice_end("w1", None, outcome="crashed", status="continuing"),
    check("c01", "passed", "1 passed"),
    ev("boss", EventType.ROUND_CLOSED, data={"passed": 2, "total": 2, "unlocked": True}),
]


def test_every_figure_equals_a_recomputation_from_the_ledger():
    report = build_report(EVENTS)
    assert report.total == total(EVENTS)
    assert report.by_actor == totals_by(EVENTS, lambda e: e.actor)
    assert sum(t.cost_micros for t in report.by_actor.values()) == report.total.cost_micros
    assert report.total.cost_micros == 48_300 + 5_896
    assert report.total.unknown_cost_events == 1
    assert report.by_actor["boss"].cost_micros == 48_300
    assert report.by_actor["worker:w1"].cost_micros == 5_896


def test_latest_check_result_wins():
    report = build_report(EVENTS)
    assert [(c.check, c.status) for c in report.checks] == [("c01", "passed"), ("c02", "passed")]


def test_worker_line_uses_the_last_slice():
    [w] = build_report(EVENTS).workers
    assert (w.worker, w.task, w.model, w.slices) == ("w1", "t1", "haiku", 2)
    assert (w.outcome, w.status, w.reason) == ("crashed", "continuing", "because")


def test_round_and_approval():
    report = build_report(EVENTS)
    assert report.approved
    [r] = report.rounds
    assert (r.n, r.passed, r.total, r.unlocked) == (1, 2, 2, True)
    assert not build_report(EVENTS[2:]).approved
    forged = ev("boss", EventType.APPROVED, round=0, data={"hashes": {}})
    assert not build_report([forged, *EVENTS[2:]]).approved


def test_rendered_text_labels_estimates_and_unknown_costs():
    text = render_report(build_report(EVENTS))
    assert "Spend (estimated by the CLI, not a bill)" in text
    assert "boss         $0.0483" in text
    assert "worker:w1    $0.0059 + 1 event(s) of unknown cost" in text
    assert "total        $0.0542 + 1 event(s) of unknown cost" in text
    assert "Round 1: 2/2 checks passed, next round unlocked" in text
    assert "c01  passed   1 passed" in text
    assert 'w1 on t1 (haiku): crashed, status continuing: "because", 2 slice(s)' in text


def test_notable_events_are_listed():
    events = [
        *EVENTS,
        ev("worker:w1", EventType.BLOCKED, data={"reason": "brief contradicts check c02"}),
        ev("boss", EventType.STOPPED, data={"reason": "worker did not start isolated"}),
    ]
    notes = build_report(events).notes
    assert notes == [
        "round 1: worker:w1 blocked (reason=brief contradicts check c02)",
        "round 1: boss stopped (reason=worker did not start isolated)",
    ]
    assert "Notes" in render_report(build_report(events))


def test_report_before_anything_ran():
    report = build_report([ev("investor", EventType.STOPPED, round=0, data={"reason": "rejected"})])
    text = render_report(report)
    assert "Approved by investor: NO" in text
    assert "No round has closed." in text
    assert "none run" in text and "none hired" in text
    assert "total        $0.0000" in text


def test_empty_or_mixed_ledgers_are_refused():
    with pytest.raises(ValueError, match="empty"):
        build_report([])
    other = Event(run="r2", round=0, actor="boss", event=EventType.STOPPED)
    with pytest.raises(ValueError, match="mixes runs"):
        build_report([EVENTS[0], other])


def test_dollars():
    assert dollars(5_896) == "$0.0059"
    assert dollars(1_250_000) == "$1.2500"


def test_a_firing_note_summarises_the_evidence_in_one_phrase():
    evidence = {"counted_slices": 3, "stalled_slices": 2, "passing": ["c01"], "missing": ["c02"]}
    fired = ev(
        "rule",
        EventType.FIRED,
        data={
            "worker": "w1",
            "task": "t1",
            "reason": "no progress",
            "evidence": evidence,
            "last_reason": None,
        },
    )
    [note] = build_report([*EVENTS, fired]).notes
    assert note == (
        "round 1: rule fired (after=3 slices, 2 without progress, 1/2 checks passing, "
        "reason=no progress, task=t1, worker=w1)"
    )


def test_disputed_checks_get_their_own_section_for_the_investor():
    data = {"task": "t1", "check": "c01", "reason": "idea says X", "worker": "w1", "slice": 1}
    disputed = [*EVENTS, ev("worker:w1", EventType.DISPUTED, data=data)]
    report = build_report(disputed)
    assert [(d.check, d.worker, d.reason) for d in report.disputes] == [
        ("c01", "w1", "idea says X")
    ]
    text = render_report(report)
    assert "Disputed checks (yours to rule on; a disputed check never counts as passing)" in text
    assert '  c01 by w1: "idea says X"' in text
    assert "Disputed checks" not in render_report(build_report(EVENTS))


def role_call(role, outcome="completed", result="ok", cost=4_000, detail="", **data) -> Event:
    data = {"role": role, "outcome": outcome, "result": result, "detail": detail, **data}
    return ev(f"role:{role}", EventType.ROLE_CALL, round=0, cost_micros=cost, data=data)


ROLE_EVENTS = [
    role_call("product_manager", detail="2 stories, 3 criteria"),
    role_call("system_designer", result="unused", detail="not used: the staged draft failed"),
    role_call("tester", outcome="api_error", result="failed", cost=2_000, detail="boom"),
    role_call("demo_writer", outcome="not_called", result="failed", cost=0),
    role_call("critic", cost=None, detail="1 verified, 0 rejected"),
]


def test_every_role_call_is_one_line_in_a_roles_section_in_ledger_order():
    lines = render_report(build_report([*EVENTS, *ROLE_EVENTS])).split("\n")
    at = lines.index("Roles (each call, in order; their spend is in the lines above)")
    assert lines[at + 1 : at + 6] == [
        "  product_manager  ok (completed), $0.0040: 2 stories, 3 criteria",
        "  system_designer  unused (completed), $0.0040: not used: the staged draft failed",
        "  tester  failed (api_error), $0.0020: boom",
        "  demo_writer  failed (not_called), $0.0000",
        "  critic  ok (completed), unknown cost: 1 verified, 0 rejected",
    ]
    assert lines[at + 6].startswith("Notes") or lines[at + 6] == ""
    assert lines.index("Workers") < at


def test_role_spend_is_in_the_spend_section_and_the_total():
    report = build_report([*EVENTS, *ROLE_EVENTS])
    assert report.total == total([*EVENTS, *ROLE_EVENTS])
    assert report.by_actor["role:tester"].cost_micros == 2_000
    assert report.total.cost_micros == 48_300 + 5_896 + 4_000 * 2 + 2_000
    text = render_report(report)
    assert "  role:product_manager $0.0040" in text
    assert "  role:critic  $0.0000 + 1 event(s) of unknown cost" in text


def test_a_report_without_role_calls_has_no_roles_section_so_old_reports_are_unchanged():
    assert "Roles" not in render_report(build_report(EVENTS))
    assert build_report(EVENTS).roles == []


def test_the_roles_section_is_built_from_role_call_events_only():
    imposter = ev("boss", EventType.BOSS_CALL, data={"role": "critic", "outcome": "completed"})
    assert build_report([*EVENTS, imposter]).roles == []
    [line] = build_report([*EVENTS, role_call("critic", detail="x")]).roles
    assert (line.role, line.outcome, line.result, line.cost_micros, line.detail) == (
        "critic",
        "completed",
        "ok",
        4_000,
        "x",
    )


def test_a_role_call_missing_its_keys_is_a_note_and_not_a_roles_line():
    broken = ev("role:critic", EventType.ROLE_CALL, round=0, data={"role": "critic"})
    report = build_report([*EVENTS, broken])
    assert report.roles == []
    assert any("role:critic role_call is incomplete (missing outcome)" in n for n in report.notes)


def test_what_a_model_wrote_in_a_role_line_is_made_safe():
    hostile = role_call("critic", result="failed", detail="\x1b[2Jline\nsk-" + "a" * 30)
    text = render_report(build_report([*EVENTS, hostile]))
    [line] = [x for x in text.split("\n") if x.startswith("  critic")]
    assert "\x1b" not in text and "\\x1b" in line and "sk-aaaa" not in line
