"""The round loop under --dispatch cascade: the ladder in order, one rung per verified failure,
the previous worker's findings handed on, and a stop that asks the investor."""

# ruff: noqa: F401, F811  (`boss` is a fixture imported from test_cli)
import json

import pytest
from test_cli import boss
from test_firm import BAD, C01, C02, C03, GOOD, events_of, run, sheet, step
from test_firm_dispatch import ModelScript, hired

from boss import dispatch
from boss.cli import EXIT_OK, EXIT_USAGE
from boss.dispatch import DispatchPolicy, plan_cascade
from boss.errors import Outcome
from boss.firm import FirmConfig
from boss.ledger import EventType, read_events
from boss.rundir import RunPaths
from boss.termsheet import Round

CONFIG = FirmConfig(dispatch=True, cascade=True, max_tier="opus")


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


def cascade_sheet(start="haiku", budget=5_000_000, config=CONFIG):
    one = sheet()
    s = one.__class__(
        one.idea,
        budget,
        (Round(1, budget, 2),),
        one.checks,
        one.tasks,
        True,
    )
    policy = DispatchPolicy(config.max_tier, config.slice_micros, cascade=True)
    return plan_cascade(s, starts={"t1": start}, profile=None, policy=policy, reads={})


def ran(worker):
    return [(s.model, s.thinking_tokens) for s in worker.specs]


def test_a_task_that_keeps_failing_climbs_the_whole_ladder_in_order_and_then_stops(paths):
    worker = ModelScript(*[step(BAD)] * 8)
    report, said = run(paths, worker, cascade_sheet(), config=CONFIG)
    assert not report.all_passed
    assert [(h["model"], h["dispatch"]["effort"]) for h in hired(paths)] == [
        ("haiku", "off"),
        ("sonnet", "off"),
        ("opus", "off"),
        ("opus", "default"),
    ]
    assert [h["dispatch"]["from_tier"] for h in hired(paths)[1:]] == ["haiku", "sonnet", "opus"]
    # effort off is a thinking budget of 0; the last rung's `default` leaves the run's own (None)
    assert [t for _, t in ran(worker)] == [0, 0, 0, 0, 0, 0, None, None]
    assert [m for m, _ in ran(worker)] == ["haiku"] * 2 + ["sonnet"] * 2 + ["opus"] * 4
    [abandoned] = events_of(paths, EventType.ABANDONED)
    assert abandoned.data["reason"].startswith("cascade: all 4 rungs failed their checks")
    assert "the investor decides" in abandoned.data["reason"]
    assert "w3 fired (no progress); w4 starts on opus/default, once" in said


def test_the_ladder_stops_at_the_first_rung_that_delivers(paths):
    worker = ModelScript(step(BAD), step(BAD), step(GOOD, "done"))
    report, _ = run(paths, worker, cascade_sheet(), config=CONFIG)
    assert report.all_passed
    assert [h["model"] for h in hired(paths)] == ["haiku", "sonnet"]
    assert events_of(paths, EventType.ABANDONED) == []


def test_a_task_starts_on_the_rung_the_chooser_gave_it(paths):
    worker = ModelScript(step(GOOD, "done"))
    run(paths, worker, cascade_sheet(start="sonnet"), config=CONFIG)
    assert [m for m, _ in ran(worker)] == ["sonnet"]
    assert hired(paths)[0]["dispatch"] == {"tier": "sonnet", "effort": "off", "why": "term sheet"}


def test_every_attempt_is_recorded_with_its_model_effort_verdict_and_cost(paths):
    worker = ModelScript(
        step(BAD, cost=7_000), step(BAD, cost=7_000), step(GOOD, "done", cost=9_000)
    )
    run(paths, worker, cascade_sheet(), config=CONFIG)
    first, second = events_of(paths, EventType.HIRED)
    assert first.data["dispatch"]["tier"] == "haiku" and second.data["dispatch"]["tier"] == "sonnet"
    ends = events_of(paths, EventType.SLICE_END)
    assert [(e.actor, e.cost_micros, e.data["model_id"]) for e in ends] == [
        ("worker:w1", 7_000, "claude-haiku-4-5-20251001"),
        ("worker:w1", 7_000, "claude-haiku-4-5-20251001"),
        ("worker:w2", 9_000, "claude-sonnet-4-5-20251001"),
    ]
    [fired] = events_of(paths, EventType.FIRED)  # the verdict on the first rung
    assert (fired.data["worker"], fired.data["reason"]) == ("w1", "no progress")
    assert {
        e.data["status"]
        for e in events_of(paths, EventType.CHECK_RESULT)
        if e.data.get("worker") == "w2"
    } == {"passed"}


def test_each_rung_is_handed_the_previous_workers_findings(paths):
    worker = ModelScript(*[step(BAD)] * 4, step(GOOD, "done"))
    run(paths, worker, cascade_sheet(), config=CONFIG)
    sonnet_first, opus_first = worker.specs[2], worker.specs[4]
    assert sonnet_first.model == "sonnet" and opus_first.model == "opus"
    for spec in (sonnet_first, opus_first):
        assert spec.resume is False  # a new worker starts from a brief, not from a session
        assert "no progress" in spec.prompt  # why the predecessor was let go
        assert "c01" in spec.prompt  # and the check it was still failing


def test_an_unverified_failure_never_moves_the_ladder(paths):
    run(paths, ModelScript(step(None, "blocked")), cascade_sheet(), config=CONFIG, answers=["s"])
    assert [h["model"] for h in hired(paths)] == ["haiku"]
    assert events_of(paths, EventType.FIRED) == []


def test_an_infrastructure_failure_is_retried_on_the_same_rung(paths):
    worker = ModelScript(step(None, outcome=Outcome.RATE_LIMITED, cost=None), step(GOOD, "done"))
    run(paths, worker, cascade_sheet(), config=CONFIG, sleeps=[])
    assert [h["model"] for h in hired(paths)] == ["haiku"]


def test_a_rung_the_round_cannot_fund_ends_the_ladder_and_asks_the_investor(paths):
    worker = ModelScript(step(BAD, cost=120_000), step(BAD, cost=120_000), step(GOOD, "done"))
    run(paths, worker, cascade_sheet(budget=400_000), config=CONFIG)
    assert [h["model"] for h in hired(paths)] == ["haiku"]
    [abandoned] = events_of(paths, EventType.ABANDONED)
    assert abandoned.data["reason"].startswith("cascade: the last worker was not fired")


def test_the_cap_and_the_run_budget_still_bound_the_ladder(paths):
    config = FirmConfig(dispatch=True, cascade=True, max_tier="opus")
    worker = ModelScript(*[step(BAD, cost=300_000)] * 8)
    s = cascade_sheet(budget=1_300_000)
    run(paths, worker, s, config=config)
    from boss import budget

    spent = budget.round_spend(read_events(paths.ledger), 1).cost_micros
    assert spent <= 1_300_000  # the round's money, not the ladder, is the limit


def test_a_sheet_edited_to_a_fifth_worker_is_refused_before_anyone_is_hired(paths):
    import dataclasses

    s = cascade_sheet()
    d = dataclasses.replace(s.tasks[0].dispatch, max_workers=5)
    s = dataclasses.replace(s, tasks=(dataclasses.replace(s.tasks[0], dispatch=d),))
    report, _ = run(paths, ModelScript(step(GOOD, "done")), s, config=CONFIG)
    assert hired(paths) == []
    assert (
        "max_workers 5 is not one of [1, 2, 3, 4]"
        in events_of(paths, EventType.STOPPED)[0].data["reason"]
    )


def test_with_cascade_off_dispatch_rules_still_steps_up_once_and_the_ledger_has_no_cascade_key(
    paths,
):
    rules = FirmConfig(dispatch=True)
    s = dispatch.plan_dispatch(
        sheet(), tier="haiku", profile=None, policy=DispatchPolicy("sonnet", 100_000), reads={}
    )
    worker = ModelScript(step(BAD), step(BAD), step(GOOD, "done"))
    run(paths, worker, s, config=rules)
    assert [h["model"] for h in hired(paths)] == ["haiku", "sonnet"]
    started = events_of(paths, EventType.STARTED)[0]
    assert "cascade" not in started.data["config"]


# --- the command line ---


def test_fund_with_cascade_shows_the_prior_the_ladder_and_the_worst_case(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", "--dispatch", "cascade")
    assert code == EXIT_OK
    assert "kind" in output and "start from" in output and "files=1 checks=1-2" in output
    assert "prior" in output and "ask you" in output
    assert "(every rung runs" in output
    [run_dir] = boss.runs()
    events = read_events(run_dir / "ledger.jsonl")
    [started] = [e for e in events if e.event is EventType.STARTED]
    assert started.data["config"]["cascade"] is True and started.data["config"]["dispatch"] is True
    saved = json.loads((run_dir / "term_sheet.json").read_text())
    assert saved["tasks"][0]["dispatch"]["effort"] == "off"


def test_cascade_is_a_flag_choice_and_rules_and_off_are_unchanged(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", "--dispatch", "rules")
    assert code == EXIT_OK and "start from" not in output and "sonnet, once" in output
    code, output = boss(
        "fund", "Reverse a string.", "--budget", "0.50", "--dispatch", "cascade", "--reserve", "0.2"
    )
    assert code == EXIT_USAGE and "--reserve cannot be used with --dispatch cascade" in output


def test_boss_routing_prints_the_view_for_a_project_with_and_without_runs(boss):
    code, output = boss("routing")
    assert code == EXIT_OK and "No recorded attempts" in output and "Priors" in output
    boss("fund", "Reverse a string.", "--budget", "0.50")
    code, output = boss("routing")
    assert code == EXIT_OK and "Runs read: 1; left out: 0" in output
    assert "files=1 checks=1-2  fresh" in output and "measured" not in output.split("Priors")[0]
