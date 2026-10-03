"""The board report with held-out checks: visible and held-out results apart, every wording the
ledger can produce, and nothing new for a run that never asked."""

import pytest

from boss.held_out import EXAMINER_ACTOR
from boss.ledger import Event, EventType
from boss.report import build_report, render_report
from boss.roles.examiner import EXAMINER

HASHES = {"manifest.json": "0" * 64, "test_h01.py": "1" * 64, "test_h02.py": "2" * 64,
          "test_h03.py": "3" * 64}  # fmt: skip


def ev(actor, event, round=1, **fields) -> Event:
    return Event(run="r1", round=round, actor=actor, event=event, **fields)


def visible(check_id, status, detail="") -> Event:
    data = {"check": check_id, "status": status, "detail": detail}
    return ev("gate", EventType.CHECK_RESULT, data=data | {"task": "t1", "scope": "product"})


def held(check_id, status, detail="") -> Event:
    data = {"check": check_id, "status": status, "detail": detail, "scope": "held_out"}
    return ev("gate", EventType.CHECK_RESULT, data=data)


def approved(hashes=HASHES) -> Event:
    data = {"hashes": {"term_sheet": "a"}} | ({"held_out_hashes": hashes} if hashes else {})
    return ev("investor", EventType.APPROVED, round=0, data=data)


def started(held_out=0) -> Event:
    return ev("boss", EventType.STARTED, round=0, data={"config": {"held_out": held_out}})


def examiner_call(outcome="completed", kept=0, problems=(), requested=3) -> Event:
    data = {"role": "examiner", "outcome": outcome, "requested": requested, "kept": kept}
    return ev(
        EXAMINER_ACTOR, EventType.ROLE_CALL, cost_micros=20_000,
        data=data | {"problems": list(problems)},
    )  # fmt: skip


def text(*events) -> str:
    return render_report(build_report(list(events)))


def held_section(report_text: str) -> list[str]:
    lines = report_text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Held-out checks"))
    end = next((i for i in range(start, len(lines)) if lines[i] == ""), len(lines))
    return lines[start:end]


def test_the_examiners_actor_name_is_the_one_the_report_looks_for():
    assert EXAMINER_ACTOR == EXAMINER.actor == "role:examiner"


def test_visible_and_held_out_results_are_shown_apart_with_the_documented_wording():
    events = [
        started(3), approved(), examiner_call(kept=3),
        visible("c01", "passed", "1 passed"), visible("c02", "passed", "1 passed"),
        held("h01", "passed", "1 passed"), held("h02", "failed", "pytest exited 1"),
        held("h03", "passed", "1 passed"),
    ]  # fmt: skip
    report = build_report(events)
    assert [(c.check, c.status) for c in report.checks] == [("c01", "passed"), ("c02", "passed")]
    assert [(c.check, c.status) for c in report.held_out] == [
        ("h01", "passed"), ("h02", "failed"), ("h03", "passed"),
    ]  # fmt: skip
    shown = render_report(report)
    assert held_section(shown) == [
        "Held-out checks: 2 of 3 passed on the product; the workers never saw them.",
        "  h01  passed   1 passed",
        "  h02  failed   pytest exited 1",
        "  h03  passed   1 passed",
    ]
    checks = shown.split("Checks\n")[1].split("\n\n")[0]
    assert "c01  passed" in checks and "h0" not in checks  # the visible list is the visible list


def test_a_held_out_result_never_replaces_a_visible_one_of_the_same_id():
    events = [approved(), visible("c01", "passed"), held("c01", "failed")]
    report = build_report(events)
    assert [(c.check, c.status) for c in report.checks] == [("c01", "passed")]
    assert [(c.check, c.status) for c in report.held_out] == [("c01", "failed")]


def test_the_latest_held_out_result_of_a_check_wins():
    report = build_report([approved(), held("h01", "failed"), held("h01", "passed")])
    assert [(c.check, c.status) for c in report.held_out] == [("h01", "passed")]


def test_checks_approved_but_only_partly_graded_say_how_many_were_not():
    [line, *_] = held_section(text(approved(), held("h01", "passed")))
    assert line == (
        "Held-out checks: 1 of 3 passed on the product (2 not graded); the workers never saw them."
    )


def test_checks_approved_and_never_graded_say_so():
    [line] = held_section(text(approved()))
    assert line == (
        "Held-out checks: 3 approved, none graded on the product (the run ended before its "
        "verdict); the workers never saw them."
    )


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            examiner_call("completed", problems=["check 'h02': source must be a fragment"]),
            "Held-out checks: none. The examiner's output was not kept: check 'h02': source "
            "must be a fragment; the run went on without them.",
        ),
        (
            examiner_call("timeout", problems=["timed out"]),
            "Held-out checks: none. The examiner's call ended timeout: timed out; the run went "
            "on without them.",
        ),
        (
            examiner_call("skipped", problems=["round 1 could not then fund a worker slice"]),
            "Held-out checks: none. The examiner was not called (round 1 could not then fund a "
            "worker slice); the run went on without them.",
        ),
    ],
)
def test_an_examiner_that_kept_nothing_is_named_with_why_and_the_run_is_said_to_have_gone_on(
    call, expected
):
    assert held_section(text(started(3), approved(None), call)) == [expected]


def test_the_reason_is_model_text_so_it_is_one_masked_line():
    nasty = "bad\x1b[31m\nAPI key sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789 here"
    [line] = held_section(text(started(3), approved(None), examiner_call(problems=[nasty])))
    assert "\x1b" not in line and "sk-ant-api03-abcdef" not in line and "\n" not in line


def test_held_out_checks_requested_but_no_examiner_call_recorded_is_said():
    [line] = held_section(text(started(3), approved(None)))
    assert line == (
        "Held-out checks: 3 were requested, but no examiner call is recorded; the run had none."
    )


@pytest.mark.parametrize("events", [
    [started(0), approved(None), visible("c01", "passed")],
    [approved(None), visible("c01", "passed")],  # a ledger from before the feature existed
    [ev("boss", EventType.STARTED, round=0, data={"config": {}}), approved(None)],
])  # fmt: skip
def test_a_run_that_never_asked_for_held_out_checks_shows_nothing_about_them(events):
    report = build_report(events)
    assert report.held_out == [] and "eld-out" not in render_report(report)


def test_the_examiners_spend_is_listed_with_every_other_actors():
    shown = text(started(3), approved(), examiner_call(kept=3), held("h01", "passed"))
    assert "role:examiner $0.0200" in shown


def test_a_held_out_result_missing_its_status_is_listed_as_incomplete_not_indexed():
    broken = ev("gate", EventType.CHECK_RESULT, data={"check": "h01", "scope": "held_out"})
    report = build_report([approved(), broken])
    assert report.held_out == []
    assert any("check_result is incomplete (missing status)" in n for n in report.notes)


def test_checks_the_examiner_wrote_that_the_approval_does_not_cover_are_said_not_to_have_run():
    # e.g. the investor rejected the term sheet: the files were written, nothing was approved
    [line] = held_section(text(started(3), approved(None), examiner_call(kept=3)))
    assert line == (
        "Held-out checks: the examiner wrote 3, but the investor's approval does not cover "
        "them; none ran."
    )


def test_a_ledger_that_names_a_held_out_result_with_no_approval_still_counts_what_was_graded():
    [line, *_] = held_section(text(held("h01", "passed"), held("h02", "failed")))
    assert line == "Held-out checks: 1 of 2 passed on the product; the workers never saw them."
