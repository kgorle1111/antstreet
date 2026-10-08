"""Report edge cases: odd ledgers, note formatting, and rendering of extreme values."""

import pytest

from antstreet.ledger import Billing, Event, EventType
from antstreet.report import build_report, dollars, render_report


def ev(actor, event, round=1, run="r1", **fields) -> Event:
    return Event(run=run, round=round, actor=actor, event=event, **fields)


def check(check_id, status, detail="", **kw) -> Event:
    return ev(
        "gate",
        EventType.CHECK_RESULT,
        data={"check": check_id, "status": status, "detail": detail},
        **kw,
    )


def hired(name, task="t1", model="haiku") -> Event:
    return ev("boss", EventType.HIRED, data={"worker": name, "task": task, "model": model})


def slice_end(worker, outcome="completed", status=None, cost=0) -> Event:
    return ev(
        f"worker:{worker}",
        EventType.SLICE_END,
        cost_micros=cost,
        billing=Billing.SUBSCRIPTION,
        data={"outcome": outcome, "status": status},
    )


def notes(*events) -> list[str]:
    return build_report([ev("boss", EventType.BOSS_CALL), *events]).notes


# --- build_report ---------------------------------------------------------------------------


def test_refusal_messages_name_the_problem():
    with pytest.raises(ValueError, match="cannot report on an empty ledger"):
        build_report([])
    with pytest.raises(ValueError, match=r"ledger mixes runs: \['r1', 'r2'\]"):
        build_report([ev("boss", EventType.BOSS_CALL), ev("boss", EventType.BOSS_CALL, run="r2")])


def test_only_an_investor_approval_counts_as_approval():
    assert not build_report([ev("boss", EventType.APPROVED)]).approved
    assert not build_report([ev("gate", EventType.APPROVED)]).approved
    assert build_report([ev("investor", EventType.APPROVED)]).approved
    assert not build_report([ev("investor", EventType.STOPPED)]).approved


def test_checks_are_listed_by_id_with_the_latest_status_and_detail():
    report = build_report(
        [
            check("c02", "failed", "old"),
            check("c01", "passed", "one"),
            check("c02", "passed", "new"),
        ]
    )
    assert [(c.check, c.status, c.detail) for c in report.checks] == [
        ("c01", "passed", "one"),
        ("c02", "passed", "new"),
    ]


def test_a_check_result_without_detail_reports_an_empty_detail():
    line = build_report(
        [ev("gate", EventType.CHECK_RESULT, data={"check": "c01", "status": "failed"})]
    ).checks[0]
    assert line.detail == ""


def test_rounds_keep_ledger_order_and_the_unlocked_flag():
    def closed(n, passed, unlocked):
        data = {"passed": passed, "total": 3, "unlocked": unlocked}
        return ev("boss", EventType.ROUND_CLOSED, round=n, data=data)

    report = build_report([closed(2, 3, True), closed(1, 1, False)])
    assert [(r.n, r.passed, r.total, r.unlocked) for r in report.rounds] == [
        (2, 3, 3, True),
        (1, 1, 3, False),
    ]


def test_a_check_result_missing_its_check_id_does_not_abort_the_whole_report():
    build_report([ev("gate", EventType.CHECK_RESULT, data={})])


def test_a_hired_event_without_a_worker_name_does_not_abort_the_whole_report():
    build_report([ev("boss", EventType.HIRED, data={})])


@pytest.mark.parametrize(
    ("event", "data", "missing"),
    [
        (EventType.CHECK_RESULT, {}, "check, status"),
        (EventType.CHECK_RESULT, {"check": "c01"}, "status"),
        (EventType.HIRED, {}, "worker"),
        (EventType.ROUND_CLOSED, {"passed": 1}, "total, unlocked"),
        (EventType.DISPUTED, {}, "check"),
    ],
)
def test_an_incomplete_event_is_shown_as_such_and_the_rest_of_the_report_survives(
    event, data, missing
):
    report = build_report([check("c09", "passed"), ev("boss", event, data=data)])
    assert [c.check for c in report.checks] == ["c09"]
    assert f"is incomplete (missing {missing})" in report.notes[-1]
    assert report.notes[-1] in render_report(report)


# --- workers --------------------------------------------------------------------------------


def test_a_hired_worker_with_no_finished_slice_says_so():
    [line] = build_report([hired("w1")]).workers
    assert (line.outcome, line.status, line.reason, line.slices) == (
        "no slice finished",
        "none",
        "",
        0,
    )


def test_a_worker_whose_last_slice_reported_no_status_reads_as_none():
    [line] = build_report([hired("w1"), slice_end("w1", status=None)]).workers
    assert (line.status, line.reason, line.slices) == ("none", "", 1)


def test_slices_are_attributed_by_worker_name_only():
    report = build_report(
        [
            hired("w1"),
            hired("w2", task="t2", model="sonnet"),
            slice_end("w1", outcome="capped", status={"status": "continuing", "reason": "x"}),
            slice_end("w2", outcome="completed", status={"status": "done"}),
            slice_end("w1", outcome="completed", status={"status": "done", "reason": "ok"}),
            slice_end("w3"),
        ]
    )
    w1, w2 = report.workers
    assert (w1.worker, w1.task, w1.model, w1.outcome, w1.status, w1.reason, w1.slices) == (
        "w1",
        "t1",
        "haiku",
        "completed",
        "done",
        "ok",
        2,
    )
    assert (w2.worker, w2.model, w2.slices, w2.reason) == ("w2", "sonnet", 1, "")


def test_a_worker_hired_without_task_or_model_gets_empty_strings():
    [line] = build_report([ev("boss", EventType.HIRED, data={"worker": "w9"})]).workers
    assert (line.task, line.model) == ("", "")


# --- notes ----------------------------------------------------------------------------------


def test_note_lists_sorted_key_values_and_skips_none_values():
    [note] = notes(
        ev("gate", EventType.BLOCKED, round=2, data={"z": 1, "a": "x", "skip": None, "m": 0})
    )
    assert note == "round 2: gate blocked (a=x, m=0, z=1)"


def test_note_without_data_has_no_parentheses():
    assert notes(ev("investor", EventType.STOPPED, round=0)) == ["round 0: investor stopped"]


def test_only_notable_events_become_notes_in_ledger_order():
    found = notes(
        ev("boss", EventType.HIRED, data={"worker": "w"}),
        ev("boss", EventType.PAUSED, data={"until": 5}),
        check("c1", "passed"),
        ev("boss", EventType.ERROR, data={"message": "boom"}),
        ev("boss", EventType.ABANDONED, data={"task": "t1"}),
        ev("boss", EventType.REASSIGNED, data={"to": "w2"}),
        ev("boss", EventType.FIRED, data={"worker": "w"}),
    )
    assert [n.split()[3] for n in found] == ["paused", "error", "abandoned", "reassigned", "fired"]


def test_evidence_that_is_not_an_object_is_dropped_from_the_note_not_summarised():
    [note] = notes(ev("boss", EventType.FIRED, data={"worker": "w", "evidence": "text"}))
    assert note == "round 1: boss fired (worker=w)"


def test_partial_evidence_is_summarised_without_crashing():
    [note] = notes(ev("boss", EventType.FIRED, data={"evidence": {"passing": ["a", "b"]}}))
    assert note == (
        "round 1: boss fired (after=None slices, None without progress, 2/2 checks passing)"
    )


def test_a_note_never_contains_the_raw_evidence_dict():
    evidence = {"counted_slices": 3, "stalled_slices": 2, "passing": ["a"], "missing": ["b", "c"]}
    [note] = notes(ev("boss", EventType.FIRED, data={"worker": "w1", "evidence": evidence}))
    assert note == (
        "round 1: boss fired (after=3 slices, 2 without progress, 1/3 checks passing, worker=w1)"
    )
    assert "evidence" not in note and "{" not in note


# --- rendering ------------------------------------------------------------------------------


def test_dollars_rounds_to_four_places_and_handles_zero_and_large_values():
    assert dollars(0) == "$0.0000"
    assert dollars(1) == "$0.0000"
    assert dollars(50) == "$0.0001"
    assert dollars(1_234_567_890) == "$1234.5679"


def test_render_shows_thousands_separators_in_token_counts():
    report = build_report(
        [ev("boss", EventType.BOSS_CALL, cost_micros=1_500_000, tokens_in=1234567, tokens_out=89)]
    )
    text = render_report(report)
    assert "  boss         $1.5000   tokens in 1,234,567 / out 89 / cached 0" in text
    assert "  total        $1.5000   tokens in 1,234,567 / out 89 / cached 0" in text


def test_actors_with_no_spend_and_no_tokens_are_left_out_of_the_spend_table():
    text = render_report(
        build_report([ev("gate", EventType.CHECK_RESULT, data={"check": "c", "status": "p"})])
    )
    spend = text.split("Spend")[1].split("Workers")[0]
    assert "gate" not in spend
    assert "  total        $0.0000" in spend


def test_an_actor_with_only_unknown_cost_events_still_appears():
    report = build_report([ev("worker:w1", EventType.SLICE_END, cost_micros=None)])
    assert "  worker:w1    $0.0000 + 1 event(s) of unknown cost" in render_report(report)


def test_render_of_a_minimal_ledger_is_exact():
    text = render_report(build_report([ev("boss", EventType.STOPPED, round=0)]))
    assert text == (
        "BOARD REPORT  run r1\n"
        "\n"
        "Approved by investor: NO\n"
        "No round has closed.\n"
        "\n"
        "Checks\n"
        "  none run\n"
        "\n"
        "Spend (estimated by the CLI, not a bill)\n"
        "  total        $0.0000   tokens in 0 / out 0 / cached 0\n"
        "\n"
        "KPIs\n"
        "  Delivered: NO (nothing was built)\n"
        "  False pass: no (the product did not pass every visible check)\n"
        "  Cost: $0.0000 (estimated)\n"
        "  Time: not recorded\n"
        "  Investor questions: 0\n"
        "\n"
        "Workers\n"
        "  none hired\n"
        "\n"
        "Notes\n"
        "  round 0: boss stopped\n"
    )


def test_worker_line_quotes_the_reason_only_when_there_is_one():
    text = render_report(
        build_report(
            [
                hired("w1"),
                slice_end("w1", status={"status": "blocked", "reason": "need key"}),
                hired("w2"),
                slice_end("w2", status={"status": "done"}),
            ]
        )
    )
    assert 'w1 on t1 (haiku): completed, status blocked: "need key", 1 slice(s)' in text
    assert "w2 on t1 (haiku): completed, status done, 1 slice(s)" in text
