"""The cascade's pure parts: the ladder, the start-tier chooser, what past runs may teach it, and
the dispatch table that shows the result. No model calls."""

import dataclasses
import json
import random
from pathlib import Path

import pytest

from antstreet import dispatch, routing, signing
from antstreet.approval import content_hashes
from antstreet.dispatch import (
    DispatchPolicy,
    DispatchView,
    RunLevel,
    cascade_hire,
    ladder,
    next_rung,
    plan_cascade,
    render_table,
    rungs_from,
    worst_case_micros,
)
from antstreet.firm import FirmConfig, config_data
from antstreet.ledger import Event, EventType
from antstreet.routing import Attempt, Choice, Stats, choose_start, read_runs, task_kind
from antstreet.rundir import RunPaths
from antstreet.termsheet import CheckSpec, Round, Task, TermSheet

CASCADE = DispatchPolicy("opus", 100_000, cascade=True)
KIND = "files=1 checks=1-2"


def sheet(budget=5_000_000, paths=("rev.py",), checks=2):
    task = Task("t1", "Create rev.py.", paths)
    specs = tuple(CheckSpec(f"c0{i}", "d", f"test_c0{i}.py", "t1") for i in range(1, checks + 1))
    return TermSheet("Reverse.", budget, (Round(1, budget, checks),), specs, (task,))


def planned(s=None, start="haiku", policy=CASCADE):
    s = s or sheet()
    return plan_cascade(s, starts={"t1": start}, profile=None, policy=policy, reads={})


def attempts(tier, n, fails, *, retry=False, cost=200_000, kind=KIND):
    return [Attempt(kind, retry, tier, i < fails, cost) for i in range(n)]


# --- the ladder ---


def test_the_ladder_is_haiku_sonnet_opus_then_opus_at_the_next_effort_and_nothing_after():
    assert ladder("opus") == (
        ("haiku", "off"),
        ("sonnet", "off"),
        ("opus", "off"),
        ("opus", "default"),
    )
    walked = [("haiku", "off")]
    while (rung := next_rung(*walked[-1], "opus")) is not None:
        walked.append(rung)
    assert walked == list(ladder("opus"))
    assert next_rung("opus", "default", "opus") is None  # then the investor is asked


def test_a_lower_ceiling_gives_a_shorter_ladder_that_still_ends_one_effort_step_up():
    assert ladder("sonnet") == (("haiku", "off"), ("sonnet", "off"), ("sonnet", "default"))
    assert rungs_from("sonnet", "opus") == ladder("opus")[1:]
    assert rungs_from("opus", "opus") == (("opus", "off"), ("opus", "default"))


def test_a_rung_is_hired_only_after_a_failure_the_gate_decided_on_evidence():
    d = planned().tasks[0].dispatch
    first = dispatch.first_hire(d)
    args = dict(stalled_slices=2, max_tier="opus", remaining_micros=5_000_000, slice_micros=100_000)
    for reason in ("no progress", "slice limit"):
        hire = cascade_hire(d, first, fired_for=reason, **args)
        assert hire is not None and (hire.tier, hire.effort) == ("sonnet", "off")
    for reason in ("blocked", "infrastructure: rate_limited", "disputed", ""):
        assert cascade_hire(d, first, fired_for=reason, **args) is None


def test_the_cascade_stops_when_the_next_rung_is_not_funded_or_the_task_allows_no_step():
    d = planned().tasks[0].dispatch
    first = dispatch.first_hire(d)
    args = dict(fired_for="no progress", stalled_slices=2, max_tier="opus", slice_micros=100_000)
    assert cascade_hire(d, first, remaining_micros=200_000, **args) is None  # sonnet needs 0.35
    off = dataclasses.replace(d, escalate_to="none")
    assert cascade_hire(off, first, remaining_micros=5_000_000, **args) is None


def test_the_plan_gives_a_task_one_worker_per_rung_from_its_start_tier():
    assert planned(start="haiku").tasks[0].dispatch.max_workers == 4
    assert planned(start="sonnet").tasks[0].dispatch.max_workers == 3
    assert planned(start="opus").tasks[0].dispatch.max_workers == 2
    d = planned(start="sonnet").tasks[0].dispatch
    assert (d.tier, d.effort, d.escalate_to) == ("sonnet", "off", "opus")


def test_the_whitelist_allows_four_workers_only_under_the_cascade():
    s = planned()
    assert dispatch.dispatch_problems(s, CASCADE) == []
    rules = DispatchPolicy("opus", 100_000)
    assert any(
        "max_workers 4 is not one of [1, 2]" in p for p in dispatch.dispatch_problems(s, rules)
    )
    five = dataclasses.replace(
        s.tasks[0], dispatch=dataclasses.replace(s.tasks[0].dispatch, max_workers=5)
    )
    assert dispatch.dispatch_problems(dataclasses.replace(s, tasks=(five,)), CASCADE)


def test_a_task_with_no_check_is_refused_under_the_cascade_because_nothing_could_verify_it():
    s = dataclasses.replace(planned(), checks=())
    assert any("has no check" in p for p in dispatch.dispatch_problems(s, CASCADE))


# --- worst case, and the table the investor reads ---


def test_the_worst_case_prices_every_rung_at_its_stalled_slices_and_its_own_reserve():
    # each rung: 2 stalled slices of (cap $0.10 + that tier's reserve): haiku 0.10, sonnet 0.30,
    # opus 0.50, opus again 0.50 -> 2 * (0.2 + 0.4 + 0.6 + 0.6) = $3.60
    assert worst_case_micros(planned(), CASCADE, 2) == 3_600_000
    assert worst_case_micros(planned(start="opus"), CASCADE, 2) == 2_400_000


def view(s, choices=None):
    level = RunLevel("haiku", "off", 0, 1)
    start = {"tier": "haiku", "effort": "off", "kind": KIND, "source": "prior", "why": "cold"}
    return DispatchView(CASCADE, level, 2, {}, choices or {"t1": start})


def test_the_table_shows_kind_start_source_ladder_and_the_worst_case():
    lines = render_table(planned(), view(planned()))
    text = "\n".join(lines)
    assert "kind" in lines[3] and "start from" in lines[3]
    assert f"t1    {KIND}  prior" in text
    assert "sonnet > opus > opus/default > ask you" in text
    assert "Worst case if every task steps up: $3.60 of $5.00 (every rung runs 2 slices)" in text


def test_the_table_says_measured_with_the_sample_and_warns_when_the_worst_case_is_over_budget():
    s = planned(sheet(budget=2_000_000))
    text = "\n".join(render_table(s, view(s, {"t1": {"kind": KIND, "source": "measured, n=12"}})))
    assert "measured, n=12" in text and "(OVER the budget" in text


def test_without_the_cascade_the_table_is_the_one_it_always_was():
    rules = DispatchPolicy("sonnet", 100_000)
    s = dispatch.plan_dispatch(sheet(), tier="haiku", profile=None, policy=rules, reads={})
    lines = render_table(s, DispatchView(rules, RunLevel("haiku", "off", 0, 1), 2, {}))
    assert lines[3].split() == [
        "task",
        "agent",
        "model",
        "effort",
        "if",
        "fired",
        "context",
        "slice",
        "cap",
    ]
    assert (
        "(every rung" not in "\n".join(lines)
        and "1 slices, then one at the new price" not in lines[-1]
    )
    assert "2 slices, then one at the new price" in lines[-1]


def test_the_cascade_flag_is_off_by_default_and_leaves_the_recorded_config_as_it_was():
    plain = config_data(FirmConfig())
    assert "cascade" not in plain and "dispatch" not in plain
    rules = config_data(FirmConfig(dispatch=True))
    assert "cascade" not in rules and rules["dispatch"] is True
    on = config_data(FirmConfig(dispatch=True, cascade=True))
    assert on["cascade"] is True
    assert DispatchPolicy("sonnet", 100_000).cascade is False
    with pytest.raises(ValueError, match="needs dispatch"):
        FirmConfig(cascade=True)


# --- the start-tier chooser ---


def test_the_start_tier_is_haiku_when_its_measured_fail_rate_is_low():
    stats = Stats(tuple(attempts("haiku", 10, 1)))
    choice = choose_start(stats, KIND, top="opus")
    assert choice.tier == "haiku" and choice.source == "measured, n=10"


def test_the_start_tier_is_sonnet_when_haikus_measured_fail_rate_is_high():
    stats = Stats(tuple(attempts("haiku", 10, 9)))
    choice = choose_start(stats, KIND, top="opus")
    assert choice.tier == "sonnet"
    assert choice.expected["sonnet"] < choice.expected["haiku"]
    assert choice.source == "prior"  # sonnet has no data of its own, and says so


def test_the_chooser_uses_the_priors_below_the_sample_minimum_and_says_so():
    four = Stats(tuple(attempts("haiku", routing.MIN_SAMPLE - 1, routing.MIN_SAMPLE - 1)))
    choice = choose_start(four, KIND, top="opus")
    assert choice.tier == "haiku" and choice.source == "prior"  # four straight failures: ignored
    five = Stats(tuple(attempts("haiku", routing.MIN_SAMPLE, routing.MIN_SAMPLE)))
    assert choose_start(five, KIND, top="opus").tier == "sonnet"  # the fifth makes it data
    assert four.estimate(KIND, False, "haiku") == routing.PRIORS["haiku"]
    assert five.estimate(KIND, False, "haiku").measured


def test_haiku_first_stays_cheaper_until_it_fails_about_two_thirds_of_the_time():
    # c_haiku is a third of c_sonnet: E[haiku] < E[sonnet] while p < 1 - c_h / E[sonnet], about 0.7
    for fails, tier in ((6, "haiku"), (8, "sonnet")):
        stats = Stats(tuple(attempts("haiku", 10, fails, cost=215_000)))
        assert choose_start(stats, KIND, top="opus").tier == tier, fails


def test_the_expected_cost_is_c_plus_p_times_the_next_rung_and_the_top_pays_one_effort_retry():
    p = routing.PRIORS
    empty = Stats()
    top = p["opus"].cost_micros * (1 + p["opus"].p_fail)  # opus, then once more at more effort
    assert routing.expected_cost(empty, KIND, "opus", "opus") == pytest.approx(top)
    sonnet = p["sonnet"].cost_micros + p["sonnet"].p_fail * top
    assert routing.expected_cost(empty, KIND, "sonnet", "opus") == pytest.approx(sonnet)
    haiku = p["haiku"].cost_micros + p["haiku"].p_fail * sonnet
    assert routing.expected_cost(empty, KIND, "haiku", "opus") == pytest.approx(haiku)


def test_later_rungs_are_priced_on_retries_not_on_fresh_attempts():
    # Sonnet is cheap when it starts, dear when it follows a Haiku failure: only the second counts
    # for Haiku's ladder, the first for Sonnet's own start.
    fresh = attempts("sonnet", 10, 0, cost=100_000)
    retry = attempts("sonnet", 10, 0, retry=True, cost=900_000)
    stats = Stats(tuple(fresh + retry))
    assert routing.expected_cost(stats, KIND, "sonnet", "opus") == pytest.approx(100_000)
    haiku = routing.expected_cost(stats, KIND, "haiku", "opus")
    assert haiku == pytest.approx(215_000 + 0.17 * 900_000)


def test_a_tier_the_round_cannot_fund_is_never_chosen_and_the_ceiling_bounds_the_choice():
    stats = Stats(tuple(attempts("haiku", 10, 10)))
    assert choose_start(stats, KIND, top="opus", fundable=lambda t: t == "haiku").tier == "haiku"
    assert choose_start(stats, KIND, top="sonnet").tier == "sonnet"
    assert choose_start(stats, KIND, top="haiku").tier == "haiku"


def test_the_chooser_only_ever_returns_a_whitelisted_tier_whatever_the_data():
    rng = random.Random(7)
    for _ in range(200):
        data = [
            Attempt(
                KIND,
                rng.random() < 0.5,
                rng.choice(dispatch.TIERS),
                rng.random() < 0.6,
                rng.randrange(1, 2_000_000),
            )
            for _ in range(rng.randrange(0, 60))
        ]
        top = rng.choice(dispatch.TIERS)
        choice = choose_start(Stats(tuple(data)), KIND, top=top)
        assert choice.tier in dispatch.TIERS and dispatch.rank(choice.tier) <= dispatch.rank(top)


# --- the task kind ---


@pytest.mark.parametrize(
    ("paths", "checks", "kind"),
    [
        (("a.py",), 1, "files=1 checks=1-2"),
        (("a.py", "b.py"), 3, "files=2-3 checks=3-5"),
        (("a.py", "b.py", "c.py", "d.py"), 6, "files=4+ checks=6+"),
        ((".",), 2, "files=4+ checks=1-2"),
        (("a.py", "a.py"), 5, "files=1 checks=3-5"),
    ],
)
def test_the_task_kind_buckets_files_and_checks(paths, checks, kind):
    s = sheet(paths=paths, checks=checks)
    assert task_kind(s, s.tasks[0]) == kind


# --- what past runs may teach it ---


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / ".boss").mkdir(parents=True)
    signing.load_or_create_key(signing.key_path(root))
    return root


def many_tasks(n):
    tasks = tuple(Task(f"t{i}", "d", (f"f{i}.py",)) for i in range(1, n + 1))
    checks = tuple(
        CheckSpec(f"c{i}{x}", "d", f"test_c{i}{x}.py", f"t{i}")
        for i in range(1, n + 1)
        for x in "ab"
    )
    return TermSheet("Many.", 5_000_000, (Round(1, 5_000_000, len(checks)),), checks, tasks)


def make_run(project, run_id, outcomes, *, tier="haiku", spread=False):
    """A run folder whose ledger the project's key vouches for: one worker per outcome, 'pass' or
    'fail', each costing $0.20. By default they share one task (so all but the first are retries);
    with `spread` each has a task of its own (so every attempt is fresh)."""
    s = many_tasks(len(outcomes)) if spread else sheet()
    paths = RunPaths(project / ".boss" / "runs" / run_id)
    paths.checks.mkdir(parents=True)
    for spec in s.checks:
        (paths.checks / spec.file).write_text("def test_x():\n    pass\n")
    approved = dataclasses.replace(s, approved_by_investor=True)
    (paths.root / "term_sheet.json").write_text(approved.to_json())
    with paths.writer() as ledger:

        def add(actor, kind, **data):
            ledger.append(
                Event(
                    run=run_id,
                    round=1,
                    actor=actor,
                    event=kind,
                    data=data,
                    cost_micros=data.pop("_cost", 0),
                )
            )

        ledger.append(
            Event(run=run_id, round=0, actor="investor", event=EventType.APPROVED,
                  data={"hashes": content_hashes(s, paths.checks)})
        )  # fmt: skip
        for i, outcome in enumerate(outcomes, start=1):
            w = f"w{i}"
            task = f"t{i}" if spread else "t1"
            add("boss", EventType.HIRED, worker=w, task=task, model=tier)
            add(
                f"worker:{w}",
                EventType.SLICE_END,
                slice=1,
                task="t1",
                outcome="completed",
                _cost=200_000,
            )
            for spec in (c for c in s.checks if c.task == task):
                status = "passed" if outcome == "pass" else "failed"
                add("gate", EventType.CHECK_RESULT, check=spec.id, status=status, worker=w, slice=1)
            if outcome == "fail":
                add("rule", EventType.FIRED, worker=w, reason="no progress")
    return paths


def test_verified_runs_are_read_as_attempts_with_a_kind_a_verdict_and_a_cost(project):
    make_run(project, "r1", ["fail", "pass"])
    found = read_runs(project)
    assert found.skipped == () and found.runs_read == 1
    assert found.stats.attempts == (
        Attempt(KIND, False, "haiku", True, 200_000),
        Attempt(KIND, True, "haiku", False, 200_000),
    )


def test_an_attempt_the_gate_did_not_decide_is_not_counted(project):
    paths = make_run(project, "r1", ["pass"])
    with paths.writer() as ledger:  # a worker that is blocked: no verdict, never a fail
        for kind, actor, data in (
            (EventType.HIRED, "boss", {"worker": "w2", "task": "t1", "model": "sonnet"}),
            (EventType.SLICE_END, "worker:w2", {"slice": 1, "outcome": "completed"}),
            (EventType.FIRED, "rule", {"worker": "w2", "reason": "blocked"}),
        ):
            ledger.append(
                Event(run="r1", round=1, actor=actor, event=kind, data=data, cost_micros=1)
            )
    assert len(read_runs(project).stats.attempts) == 1


def poisoned_stats(project, run_id="evil"):
    """Ten attempts on Haiku that all failed, which would send every one-file task to Sonnet."""
    return make_run(project, run_id, ["fail"] * 10, spread=True)


def test_a_verified_history_moves_the_start_tier(project):
    poisoned_stats(project)
    stats = read_runs(project).stats
    assert choose_start(stats, KIND, top="opus").tier == "sonnet"  # the control: it does steer


def test_a_run_whose_ledger_was_edited_is_left_out_and_never_steers_the_choice(project):
    paths = poisoned_stats(project)
    lines = paths.ledger.read_text().splitlines()
    forged = json.loads(lines[4])
    forged["cost_micros"] = 1  # any byte of any line breaks the chain
    lines[4] = json.dumps(forged, sort_keys=True)
    paths.ledger.write_text("\n".join(lines) + "\n")
    found = read_runs(project)
    assert [run for run, _ in found.skipped] == ["evil"] and found.stats.attempts == ()
    assert choose_start(found.stats, KIND, top="opus").tier == "haiku"


def test_a_run_forged_without_the_key_is_left_out(project):
    paths = RunPaths(project / ".boss" / "runs" / "evil")
    paths.checks.mkdir(parents=True)
    s = sheet()
    for spec in s.checks:
        (paths.checks / spec.file).write_text("def test_x():\n    pass\n")
    (paths.root / "term_sheet.json").write_text(
        dataclasses.replace(s, approved_by_investor=True).to_json()
    )
    from antstreet.ledger import LedgerWriter

    with LedgerWriter(paths.ledger) as ledger:  # a chained ledger with an approval nobody signed
        ledger.append(Event(run="evil", round=0, actor="investor", event=EventType.APPROVED,
                            data={"hashes": content_hashes(s, paths.checks)}))  # fmt: skip
        for i in range(10):
            w = f"w{i}"
            ledger.append(
                Event(
                    run="evil",
                    round=1,
                    actor="boss",
                    event=EventType.HIRED,
                    data={"worker": w, "task": "t1", "model": "haiku"},
                )
            )
    found = read_runs(project)
    assert found.stats.attempts == () and [r for r, _ in found.skipped] == ["evil"]


def test_a_term_sheet_edited_after_approval_is_left_out(project):
    paths = poisoned_stats(project)
    edited = paths.root / "term_sheet.json"
    edited.write_text(edited.read_text().replace("f1.py", "g1.py"))
    found = read_runs(project)
    assert found.stats.attempts == () and "match no signed approval" in found.skipped[0][1]


def test_a_check_file_edited_after_approval_is_left_out(project):
    paths = poisoned_stats(project)
    (paths.checks / "test_c1a.py").write_text("def test_x():\n    assert True\n")
    assert read_runs(project).stats.attempts == ()


def test_a_deleted_anchor_or_dropped_tail_is_left_out(project):
    paths = poisoned_stats(project)
    lines = paths.ledger.read_text().splitlines()
    paths.ledger.write_text("\n".join(lines[:-2]) + "\n")  # drop the last two events
    assert read_runs(project).stats.attempts == ()
    clean = make_run(project, "ok", ["pass"])
    assert len(read_runs(project).stats.attempts) == 1 and clean.ledger.exists()


def test_without_an_investor_key_nothing_is_verifiable_so_nothing_is_read(project):
    make_run(project, "r1", ["fail"] * 6)
    signing.key_path(project).unlink()
    found = read_runs(project)
    assert found.stats.attempts == () and "no investor key" in found.skipped[0][1]


def test_a_project_with_no_runs_reads_as_nothing(tmp_path):
    found = read_runs(tmp_path)
    assert found.stats.attempts == () and found.runs_read == 0 and found.skipped == ()


# --- the view ---


def test_the_routing_view_prints_per_kind_and_tier_the_attempts_fail_rate_cost_start_and_why(
    project,
):
    make_run(project, "r1", ["fail", "fail", "fail", "fail", "fail", "pass"])
    make_run(project, "r2", ["pass"])
    text = "\n".join(routing.render_routing(read_runs(project), top="opus"))
    print(text)
    assert "Runs read: 2; left out: 0" in text
    assert "files=1 checks=1-2  fresh" in text and "haiku  6" in text or "haiku" in text
    assert "measured, n=" in text
    assert "Chosen start tier" in text and "lowest expected cost" in text


def test_the_routing_view_names_a_run_it_left_out_and_why(project):
    paths = make_run(project, "r1", ["pass"])
    paths.ledger.write_text(paths.ledger.read_text()[:-5])
    text = "\n".join(routing.render_routing(read_runs(project), top="opus"))
    assert "Runs read: 0; left out: 1" in text and "r1:" in text
    assert "No recorded attempts: every kind starts from the priors" in text


# --- the router's start: tier, effort, reason and features, from the term sheet alone ---


def bench_shaped(idea="Build it.", files=("a.py",), checks=8):
    """The shapes the benchmark's firm cells had: one module with 6+ checks, or 2-3 modules."""
    task = Task("t1", "Create it.", files)
    specs = tuple(CheckSpec(f"c{i:02}", "d", f"test_c{i:02}.py", "t1") for i in range(checks))
    return TermSheet(idea, 800_000, (Round(1, 800_000, checks),), specs, (task,))


def start_of(s, stats=None):
    return routing.starts_for(s, stats or Stats(), top="opus", fundable=lambda _t: True)["t1"]


@pytest.mark.parametrize(
    ("files", "checks", "kind"),
    [
        (("bytesize.py",), 8, "files=1 checks=6+"),
        (("store.py", "cli.py", "report.py"), 8, "files=2-3 checks=6+"),
        (("a.py",), 4, "files=1 checks=3-5"),
    ],
)
def test_a_cold_start_begins_on_haiku_at_effort_off_and_says_why(files, checks, kind):
    record = start_of(bench_shaped(files=files, checks=checks)).record("opus")
    assert (record["tier"], record["effort"], record["kind"]) == ("haiku", "off", kind)
    assert record["source"] == "prior"
    assert str(record["why"]).startswith("cold start, under 5 verified attempts of this kind")
    assert record["features"] == {
        "idea_chars": 9,
        "tasks": 1,
        "files": len(files),
        "checks": checks,
    }


def test_a_measured_start_does_not_call_itself_a_cold_start():
    choice = start_of(
        bench_shaped(), Stats(tuple(attempts("haiku", 10, 1, kind="files=1 checks=6+")))
    )
    assert choice.source == "measured, n=10" and "cold start" not in choice.why


def test_the_start_effort_is_the_first_rung_of_the_ladder_from_the_chosen_tier():
    stats = Stats(tuple(attempts("haiku", 10, 9, kind="files=1 checks=6+")))
    record = start_of(bench_shaped(), stats).record("opus")
    assert (record["tier"], record["effort"]) == ("sonnet", "off")
    assert Choice("k", "opus", {}, "prior", "w").record("opus")["effort"] == "off"


def test_the_table_shows_the_routers_start_and_reason_before_the_worst_case():
    s = planned()
    start = {"tier": "haiku", "effort": "off", "kind": KIND, "source": "prior", "why": "cold x"}
    lines = render_table(s, view(s, {"t1": start}))
    reason = lines.index("Router's start for t1: haiku/off, cold x")
    assert reason < next(i for i, x in enumerate(lines) if x.startswith("Worst case"))


def test_no_benchmark_label_can_reach_the_start_tier():
    # Leakage guard: the router reads the term sheet only. Two sheets that differ only in what a
    # benchmark knows (a difficulty word of the same length) get the same start, reason and record.
    hard, easy = bench_shaped(idea="difficulty: hard"), bench_shaped(idea="difficulty: easy")
    assert start_of(hard).record("opus") == start_of(easy).record("opus")
    assert set(routing.features(hard, hard.tasks[0])) == {"idea_chars", "tasks", "files", "checks"}
    source = Path(routing.__file__).read_text(encoding="utf-8")
    for leak in ("difficulty", "meta.json", "hidden_checks", "antstreet.bench"):
        assert leak not in source, leak
