"""The report's Models section: the boss's and roles' requested and observed models (R2).

A ledger from before `model_observed` existed must still report, and say "not recorded" rather
than pass off the requested model as the one that ran.
"""

from boss_init import BOSS_INIT
from docs_support import run_cli

from antstreet.ledger import Event, EventType
from antstreet.report import build_report, render_report

RAN = "claude-opus-5-5"


def call(actor: str, event: EventType, **data) -> Event:
    return Event(run="r1", round=0, actor=actor, event=event, cost_micros=1, data=data)


def test_the_report_lists_each_requested_and_observed_model_with_its_calls():
    events = [
        call("boss", EventType.BOSS_CALL, model="opus", model_observed=RAN, outcome="capped"),
        call("boss", EventType.BOSS_CALL, model="opus", model_observed=RAN, outcome="completed"),
        call(
            "role:critic",
            EventType.ROLE_CALL,
            role="critic",
            outcome="timeout",
            model="haiku",
            model_observed=None,
        ),
        call(
            "role:examiner",
            EventType.ROLE_CALL,
            role="examiner",
            outcome="skipped",
            model="haiku",
            model_observed=None,
        ),
    ]
    text = render_report(build_report(events))
    assert f"  boss  opus -> {RAN} (2 calls)" in text
    assert "  role:critic  haiku -> not reported by the CLI (1 call)" in text
    assert "examiner  haiku" not in text  # a call never made ran no model


def test_an_old_ledger_without_the_field_still_reports_and_says_not_recorded():
    events = [
        call("boss", EventType.BOSS_CALL, model="haiku", outcome="completed"),
        call("role:critic", EventType.ROLE_CALL, role="critic", outcome="completed", model="haiku"),
    ]
    report = build_report(events)
    assert [m.recorded for m in report.models] == [False, False]
    text = render_report(report)
    assert "  boss  haiku -> not recorded (the ledger predates model_observed) (1 call)" in text


def test_an_observed_model_is_masked_on_its_way_into_the_report():
    events = [call("boss", EventType.BOSS_CALL, model="haiku", model_observed="a\nb", outcome="x")]
    assert "  boss  haiku -> a b (1 call)" in render_report(build_report(events))


def test_the_saved_report_of_a_fund_run_names_the_model_the_boss_ran(tmp_path):
    # The fake CLI's init always says Haiku 4.5, so asking for sonnet shows the two apart.
    _, run_dir, _ = run_cli(
        tmp_path, ["fund", "Reverse a string.", "--budget", "0.50", "--boss-model", "sonnet"]
    )
    text = (run_dir / "report.md").read_text()
    assert f"  boss  sonnet -> {BOSS_INIT['model']} (1 call)" in text
