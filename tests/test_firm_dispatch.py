"""The round loop under --dispatch: each worker on the model its task was given, a step up only on
the gate's evidence, the real model checked, and the exact text of every slice recorded."""

import dataclasses
import hashlib
import uuid

import pytest
from test_firm import (
    BAD,
    C01,
    C02,
    C03,
    GOOD,
    HALF,
    Script,
    dispute,
    events_of,
    run,
    sheet,
    step,
)

from boss import context, dispatch, held_out
from boss.approval import content_hashes
from boss.dispatch import DispatchPolicy, plan_dispatch
from boss.errors import Outcome
from boss.firm import FirmConfig
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.report import build_report, render_report
from boss.rule import FiringPolicy
from boss.rundir import RunPaths
from boss.termsheet import Round
from boss.worker import (
    SCHEMA_TOOL,
    WORKER_TOOLS,
    ModelMismatchError,
    SliceSpec,
    build_command,
    isolation_violations,
)

ON = FirmConfig(dispatch=True)


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


class ModelScript(Script):
    """A scripted worker whose init says which model ran: the one it was launched with, unless
    `ran` says otherwise."""

    def __init__(self, *steps, ran=None):
        super().__init__(*steps)
        self.ran = ran

    def __call__(self, spec, workspace, log_path, *, env):
        result = super().__call__(spec, workspace, log_path, env=env)
        model = self.ran(spec) if callable(self.ran) else self.ran
        if model is None:
            model = f"claude-{spec.model}-4-5-20251001"
        return dataclasses.replace(result, model_id=model)


def planned(s=None, config=ON, **changes):
    s = s or sheet()
    s = plan_dispatch(
        s,
        tier="haiku",
        profile=None,
        policy=DispatchPolicy(config.max_tier, config.slice_micros),
        reads={},
    )
    if changes:
        tasks = tuple(
            dataclasses.replace(t, dispatch=dataclasses.replace(t.dispatch, **changes))
            for t in s.tasks
        )
        s = dataclasses.replace(s, tasks=tasks)
    return s


def hired(paths):
    return [e.data for e in events_of(paths, EventType.HIRED)]


# --- what is recorded ---


def test_every_hire_records_its_dispatch_and_the_model_the_spec_launched(paths):
    worker = ModelScript(step(GOOD, "done"))
    report, _ = run(paths, worker, planned(), config=ON)
    assert report.all_passed
    [h] = hired(paths)
    assert h["model"] == "haiku" and h["dispatch"] == {
        "tier": "haiku",
        "effort": "default",
        "why": "term sheet",
    }
    assert [s.model for s in worker.specs] == ["haiku"]


def test_a_task_on_sonnet_launches_sonnet_and_books_the_models_own_reserve(paths):
    s = planned(tier="sonnet", escalate_to="sonnet")
    worker = ModelScript(step(GOOD, "done"))
    run(paths, worker, s, config=ON)
    assert worker.specs[0].model == "sonnet"
    [start] = events_of(paths, EventType.SLICE_START)
    # round $0.50 less a $0.30 sonnet reserve leaves a $0.20 room, capped by the $0.10 slice
    assert start.data["cap_micros"] == 100_000


def test_the_slice_cap_leaves_room_for_the_overshoot_of_the_models_own_reserve(paths):
    one = sheet()
    round_ = dataclasses.replace(one.rounds[0], budget_micros=340_000)
    s = dataclasses.replace(one, rounds=(round_,), budget_micros=340_000)
    s = planned(s, tier="sonnet", escalate_to="sonnet")
    worker = ModelScript(step(GOOD, "done"))
    run(paths, worker, s, config=ON)
    [start] = events_of(paths, EventType.SLICE_START)
    assert start.data["cap_micros"] == 40_000  # 340,000 less sonnet's 300,000, not haiku's 100,000


def test_slice_start_records_the_context_and_its_hash_equals_the_saved_prompt(paths):
    worker = ModelScript(step(HALF), step(GOOD, "done"))
    run(paths, worker, planned(), config=ON)
    starts = events_of(paths, EventType.SLICE_START)
    assert len(starts) == 2
    for event, spec in zip(starts, worker.specs, strict=True):
        number = event.data["slice"]
        saved = paths.prompt("w1", number).read_bytes()
        assert hashlib.sha256(saved).hexdigest() == event.data["context_sha256"]
        assert saved == (spec.append_system_prompt.encode() + b"\0" + spec.prompt.encode())
        assert event.data["context_chars"] == len(spec.prompt)
        assert sum(event.data["context_parts"].values()) <= len(spec.prompt)
    assert set(starts[0].data["context_parts"]) == {"task"}
    assert set(starts[1].data["context_parts"]) == {"gate"}  # a resumed slice: the gate's feedback
    assert context.verify(paths, read_events(paths.ledger)) == []


def test_slice_end_records_the_model_the_cli_says_it_ran(paths):
    run(
        paths,
        ModelScript(step(GOOD, "done"), ran="claude-haiku-4-5-20251001"),
        planned(),
        config=ON,
    )
    [end] = events_of(paths, EventType.SLICE_END)
    assert end.data["model_id"] == "claude-haiku-4-5-20251001"


def test_with_dispatch_off_the_ledger_has_exactly_the_keys_it_always_had(paths):
    run(paths, Script(step(GOOD, "done")))
    [h] = events_of(paths, EventType.HIRED)
    assert set(h.data) == {"worker", "task", "model", "prompt", "profile"}
    [start] = events_of(paths, EventType.SLICE_START)
    assert set(start.data) == {"slice", "task", "cap_micros", "session"}
    [end] = events_of(paths, EventType.SLICE_END)
    assert "model_id" not in end.data
    [started] = events_of(paths, EventType.STARTED)
    assert "dispatch" not in started.data["config"] and "max_tier" not in started.data["config"]
    assert not list((paths.root / "logs").glob("*.prompt.txt"))


def test_a_run_with_dispatch_on_records_it_in_its_config(paths):
    run(paths, ModelScript(step(GOOD, "done")), planned(), config=ON)
    [started] = events_of(paths, EventType.STARTED)
    assert started.data["config"]["dispatch"] is True
    assert started.data["config"]["max_tier"] == "sonnet"


# --- the model that really ran ---


def test_a_model_the_cli_did_not_launch_stops_the_run_and_the_slice_is_still_booked(paths):
    worker = ModelScript(step(HALF, cost=7_000), ran="claude-sonnet-4-5-20250929")
    with pytest.raises(
        ModelMismatchError, match="launched 'haiku', but the CLI ran 'claude-sonnet"
    ):
        run(paths, worker, planned(), config=ON)
    [end] = events_of(paths, EventType.SLICE_END)
    assert end.cost_micros == 7_000 and end.data["model_id"] == "claude-sonnet-4-5-20250929"
    [error] = events_of(paths, EventType.ERROR)
    assert "launched 'haiku'" in error.data["model"] and error.cost_micros is None
    assert events_of(paths, EventType.STOPPED)[-1].data["reason"].startswith("wrong model")
    assert events_of(paths, EventType.CHECK_RESULT) == []  # never gated, never judged
    assert len(worker.specs) == 1


def test_a_cli_that_reports_no_model_proves_nothing_and_stops_the_run(paths):
    class NoModel(Script):
        def __call__(self, spec, workspace, log_path, *, env):
            return Script.__call__(self, spec, workspace, log_path, env=env)  # model_id is None

    with pytest.raises(ModelMismatchError, match="the CLI reported no model"):
        run(paths, NoModel(step(GOOD, "done")), planned(), config=ON)


def test_a_slice_that_never_started_has_no_model_to_check(paths):
    class Down(ModelScript):
        def __call__(self, spec, workspace, log_path, *, env):
            result = Script.__call__(self, spec, workspace, log_path, env=env)
            return result  # model_id stays None, as when the CLI failed before init

    limited = step(None, outcome=Outcome.USAGE_LIMIT, cost=None)
    report, _ = run(paths, Down(limited), planned(), config=ON)
    assert report.stopped is not None and report.stopped.startswith("paused")
    assert events_of(paths, EventType.ERROR) == []


def test_with_dispatch_off_the_model_is_not_checked(paths):
    run(paths, Script(step(GOOD, "done")))  # a SliceRun with no model_id at all


def test_the_launch_argv_differs_between_tiers_only_in_the_model():
    argvs = []
    for model in ("haiku", "sonnet", "opus"):
        spec = SliceSpec(
            session_id=uuid.uuid4(), resume=False, prompt="p", model=model,
            cap_micros=10_000,
        )  # fmt: skip
        argv = build_command(spec, api_key=False)
        i = argv.index("--model")
        assert argv[i + 1] == model
        argvs.append([a for k, a in enumerate(argv) if k != i + 1 and a != spec.session_id.hex])
    sans_session = [[a for a in argv if len(a) != 36] for argv in argvs]
    assert sans_session[0] == sans_session[1] == sans_session[2]
    tools = argvs[0][argvs[0].index("--tools") + 1]
    assert tools == ",".join(WORKER_TOOLS)


def test_the_init_tools_check_is_the_same_whatever_the_tier():
    init = {
        "tools": [*WORKER_TOOLS, SCHEMA_TOOL], "mcp_servers": [], "permissionMode": "dontAsk",
        "claude_code_version": "2.1.285",
    }  # fmt: skip
    for model in ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-1"):
        assert isolation_violations(init | {"model": model}, hook_events=0) == []
    assert isolation_violations(init | {"tools": ["Bash", *WORKER_TOOLS]}, hook_events=0)


# --- the step up ---


def test_a_worker_fired_for_no_progress_is_replaced_one_tier_up_and_it_is_recorded(paths):
    worker = ModelScript(step(BAD), step(BAD), step(GOOD, "done"))
    report, said = run(paths, worker, planned(), config=ON)
    assert report.all_passed
    first, second = hired(paths)
    assert first["model"] == "haiku" and second["model"] == "sonnet"
    assert second["dispatch"] == {
        "tier": "sonnet",
        "effort": "default",
        "why": "predecessor fired: no progress, 2 stalled slices",
        "from_tier": "haiku",
    }
    assert [s.model for s in worker.specs] == ["haiku", "haiku", "sonnet"]
    assert "w1 fired (no progress); w2 starts on sonnet, once" in said


def test_a_slice_limit_firing_steps_up_too(paths):
    config = FirmConfig(
        dispatch=True, firing=False, policy=FiringPolicy(stall_slices=1, max_slices=1)
    )
    worker = ModelScript(step(HALF), step(GOOD, "done"))
    run(paths, worker, planned(config=config), config=config)
    [fired] = events_of(paths, EventType.FIRED)
    assert fired.data["reason"] == "slice limit"
    assert (
        hired(paths)[1]["dispatch"]["from_tier"] == "haiku" and hired(paths)[1]["model"] == "sonnet"
    )


def test_a_step_the_round_cannot_fund_steps_the_effort_instead_and_says_why(paths):
    one = sheet()
    round_ = dataclasses.replace(one.rounds[0], budget_micros=400_000)
    s = planned(
        dataclasses.replace(one, rounds=(round_,), budget_micros=400_000), escalate_to="sonnet"
    )
    worker = ModelScript(step(BAD, cost=120_000), step(BAD, cost=120_000), step(GOOD, "done"))
    run(paths, worker, s, config=ON)
    second = hired(paths)[1]
    assert (second["model"], second["dispatch"]["effort"]) == ("haiku", "high")
    assert second["dispatch"]["refused"] == "sonnet needs $0.35 free in the round; $0.16 is left"
    assert worker.specs[2].thinking_tokens == dispatch.HIGH_THINKING_TOKENS


def test_a_task_is_stepped_up_at_most_once(paths):
    worker = ModelScript(step(BAD), step(BAD), step(BAD), step(BAD))
    run(paths, worker, planned(), config=ON)
    assert [h["model"] for h in hired(paths)] == ["haiku", "sonnet"]
    assert events_of(paths, EventType.ABANDONED)[0].data["reason"] == "already reassigned once"
    assert "from_tier" not in hired(paths)[0]["dispatch"]


def test_blocked_and_disputed_workers_and_infrastructure_never_step_anyone_up(paths):
    run(paths, ModelScript(step(None, "blocked")), planned(), config=ON, answers=["s"])
    assert [h["model"] for h in hired(paths)] == ["haiku"]
    assert events_of(paths, EventType.FIRED) == []


def test_a_disputing_worker_set_aside_is_not_replaced_on_a_stronger_model(paths):
    run(
        paths,
        ModelScript(step(HALF, disputes=[dispute("c01")])),
        planned(),
        config=ON,
        answers=["s"],
    )
    assert [h["model"] for h in hired(paths)] == ["haiku"]


def test_an_infrastructure_failure_is_retried_on_the_same_model(paths):
    worker = ModelScript(step(None, outcome=Outcome.RATE_LIMITED, cost=None), step(GOOD, "done"))
    run(paths, worker, planned(), config=ON, sleeps=[])
    assert [h["model"] for h in hired(paths)] == ["haiku"]
    assert [s.model for s in worker.specs] == ["haiku", "haiku"]


def test_the_investor_can_turn_the_step_off_for_a_task(paths):
    shout = "def shout(s):\n    return s.upper() + '!'\n"
    worker = ModelScript(
        step(BAD), step(BAD), step(GOOD, "done"), step(shout, "done", name="up.py")
    )
    s = planned(sheet(two_tasks=True), escalate_to="none")
    run(paths, worker, s, config=ON)
    models = [h["model"] for h in hired(paths) if h["task"] == "t1"]
    assert models == ["haiku", "haiku"]  # replaced, never stepped up
    assert "from_tier" in hired(paths)[1]["dispatch"]  # and the record says nothing changed
    assert hired(paths)[1]["dispatch"]["refused"] == "stepping up is off for this task"


def test_on_the_one_agent_route_a_replacement_that_is_not_stronger_is_not_hired(paths):
    s = planned(escalate_to="none", max_workers=2)
    assert s.route == "one_agent"
    worker = ModelScript(step(BAD), step(BAD))
    report, _ = run(paths, worker, s, config=ON)
    assert not report.all_passed
    assert [h["model"] for h in hired(paths)] == ["haiku"]
    [abandoned] = events_of(paths, EventType.ABANDONED)
    assert abandoned.data["reason"] == "one agent: no stronger worker to hire"


def test_a_task_limited_to_one_worker_is_not_replaced(paths):
    s = planned(max_workers=1)
    run(paths, ModelScript(step(BAD), step(BAD)), s, config=ON)
    assert len(hired(paths)) == 1
    assert (
        events_of(paths, EventType.ABANDONED)[0].data["reason"]
        == "the sheet allows 1 worker for this task"
    )


# --- refused before spend ---


def approved_run(paths, s, config=ON, worker=None):
    """Run `s` with an approval for exactly that sheet, as an investor who signed it."""
    return run(paths, worker or ModelScript(step(GOOD, "done")), s, config=config)


def test_a_dispatch_outside_the_whitelist_is_refused_at_hire_even_with_a_matching_approval(paths):
    bad = planned(tier="opus", escalate_to="none")  # the investor "approved" a sheet routed to opus
    worker = ModelScript(step(GOOD, "done"))
    report, _ = approved_run(paths, bad, worker=worker)
    assert worker.specs == [] and events_of(paths, EventType.HIRED) == []
    assert "the dispatch is refused: " in events_of(paths, EventType.STOPPED)[0].data["reason"]
    assert report.stopped.startswith("stopped: the dispatch is refused")


def test_opus_is_available_only_when_the_run_allows_it(paths):
    config = FirmConfig(dispatch=True, max_tier="opus")
    round_ = Round(1, 900_000, 2)  # an opus slice needs its $0.50 reserve and a slice on top
    s = planned(
        dataclasses.replace(sheet(), rounds=(round_,), budget_micros=900_000),
        config=config,
        tier="opus",
        escalate_to="none",
    )
    worker = ModelScript(step(GOOD, "done"))
    approved_run(paths, s, config=config, worker=worker)
    assert [x.model for x in worker.specs] == ["opus"]


def test_a_sheet_that_carries_dispatch_is_refused_when_the_run_has_it_off(paths):
    worker = Script(step(GOOD, "done"))
    report, _ = run(paths, worker, planned(), config=FirmConfig())
    assert worker.specs == [] and "--dispatch is off" in report.stopped


def test_a_tier_the_round_cannot_fund_is_refused_before_anyone_is_hired(paths):
    one = sheet()
    round_ = dataclasses.replace(one.rounds[0], budget_micros=250_000)
    s = dataclasses.replace(one, rounds=(round_,), budget_micros=250_000)
    s = planned(s, tier="sonnet", escalate_to="sonnet")
    worker = ModelScript(step(GOOD, "done"))
    report, _ = approved_run(paths, s, worker=worker)
    assert worker.specs == [] and "a sonnet slice needs a round of at least" in report.stopped


def test_a_brief_too_big_for_the_bundle_is_refused_before_a_slice_starts(paths):
    huge = dataclasses.replace(planned(), idea="word " * 8_000)
    worker = ModelScript(step(GOOD, "done"))
    report, _ = approved_run(paths, huge, worker=worker)
    assert worker.specs == [] and events_of(paths, EventType.SLICE_START) == []
    assert "the brief for task t1" in report.stopped and "limit is 30000" in report.stopped


# --- resume and the ceiling ---


def test_a_resumed_run_uses_the_model_the_worker_was_hired_on_not_the_configs(paths):
    s = planned(tier="sonnet", escalate_to="sonnet")
    first = ModelScript(step(HALF, cost=5_000), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(paths, first, s, config=ON)
    resumed = ModelScript(step(GOOD, "done", cost=7_000))
    resumed.totals = dict(first.totals)
    drifted = dataclasses.replace(ON, model="opus")  # what the config says now, not what ran
    run(paths, resumed, s, config=drifted)
    # the interrupted slice was launched too: three launches, all on the model it was hired on
    assert [x.model for x in first.specs + resumed.specs] == ["sonnet"] * 3
    assert len(hired(paths)) == 1


def test_the_spend_ceiling_allows_for_the_dearest_model_a_task_can_reach():
    s = planned()
    assert dispatch.reachable_reserve(s, "sonnet") == 300_000  # haiku, stepping up to sonnet
    assert dispatch.reachable_reserve(planned(escalate_to="none"), "sonnet") == 100_000
    capped = planned(escalate_to="sonnet")
    assert dispatch.reachable_reserve(capped, "haiku") == 100_000  # the run's ceiling on tiers


def test_the_ceiling_uses_the_reachable_reserve_so_a_stepped_up_overshoot_is_not_a_breach(paths):
    # Two haiku slices overshoot the round by $0.15: over the ceiling a haiku-only run would have
    # ($0.80 + $0.10), inside the one a run that can reach sonnet has ($0.80 + $0.30).
    one = sheet()
    round_ = dataclasses.replace(one.rounds[0], budget_micros=800_000)
    s = dataclasses.replace(one, rounds=(round_,), budget_micros=800_000)
    stepping = planned(s, escalate_to="sonnet")
    flat = planned(s, escalate_to="none", max_workers=2)
    for sh, breached in ((flat, True), (stepping, False)):
        folder = paths.root.parent / f"run-{breached}"
        p = RunPaths(folder)
        p.checks.mkdir(parents=True)
        for name, code in (("test_c01.py", C01), ("test_c02.py", C02)):
            (p.checks / name).write_text(code)
        run(p, ModelScript(step(BAD, cost=500_000), step(BAD, cost=450_000)), sh, config=ON)
        reasons = [e.data["reason"] for e in events_of(p, EventType.STOPPED)]
        assert any("run ceiling" in r for r in reasons) is breached


# --- who did what, in the report ---


def test_the_report_says_who_did_what_on_which_model_at_what_cost(paths):
    worker = ModelScript(step(BAD), step(BAD, cost=20_000), step(GOOD, "done", cost=30_000))
    run(paths, worker, planned(), config=ON)
    text = render_report(build_report(read_events(paths.ledger)))
    assert "w1 on t1: haiku/default, $0.0300, 2 slices, fired (no progress)" in text
    assert (
        "w2 on t1: sonnet/default, escalated from haiku (fired: no progress), $0.0300, 1 slice, "
        "delivered" in text
    )
    report = build_report(read_events(paths.ledger))
    spent = sum(w.cost_micros or 0 for w in report.workers)
    assert (
        spent == report.by_actor["worker:w1"].cost_micros + report.by_actor["worker:w2"].cost_micros
    )
    assert spent + report.by_actor["boss"].cost_micros == report.total.cost_micros


# --- nothing outside the brief reaches a worker ---


def test_sentinels_in_held_out_other_tasks_checks_the_key_and_hidden_checks_reach_no_worker(paths):
    s = planned(sheet(two_tasks=True))
    (paths.checks / "test_c03.py").write_text("# OTHER-TASK-SENTINEL\n" + C03)
    entry = held_out.HeldOutCheck("h01", held_out.file_name("h01"), "Reverse a string.")
    held_out.write(paths.held_out, [(entry, "# HELD-OUT-SENTINEL\n" + C01)])
    with LedgerWriter(paths.ledger) as ledger:  # an approval that covers the held-out folder too
        data = {"hashes": content_hashes(s, paths.checks)}
        data["held_out_hashes"] = held_out.hashes(paths.held_out)
        ledger.append(
            Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
    key = paths.root.parent / ".boss"
    key.mkdir()
    (key / "investor.key").write_text("KEY-SENTINEL")
    (paths.root.parent / "hidden").mkdir()
    (paths.root.parent / "hidden" / "test_x.py").write_text("# HIDDEN-SENTINEL\n")
    shout = "def shout(s):\n    return s.upper() + '!'\n"
    worker = ModelScript(
        step(BAD),
        step(BAD),
        step(GOOD, "done"),
        step(shout, "done", name="up.py"),
        step(shout, "done", name="up.py"),
    )
    run(paths, worker, s, config=ON)
    seen = [x.prompt + (x.append_system_prompt or "") for x in worker.specs]
    seen += [p.read_text() for p in (paths.root / "logs").glob("*.prompt.txt")]
    assert len(seen) >= 4
    for text in seen:
        for sentinel in ("HELD-OUT-SENTINEL", "KEY-SENTINEL", "HIDDEN-SENTINEL"):
            assert sentinel not in text
    t1_texts = [x.prompt for x in worker.specs if "Create rev.py" in x.prompt]
    assert t1_texts and all("OTHER-TASK-SENTINEL" not in t for t in t1_texts)
