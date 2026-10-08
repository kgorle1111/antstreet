"""Dispatch core: the route, the whitelist, the plan, the step-up and the investor's table."""

import dataclasses
import hashlib
import json

import pytest

from antstreet import dispatch, firm
from antstreet.approval import content_hashes
from antstreet.dispatch import (
    DispatchPolicy,
    DispatchView,
    RunLevel,
    escalate,
    plan_dispatch,
    replacement_hire,
    route_of,
    route_text,
)
from antstreet.termsheet import CheckSpec, Dispatch, Round, Task, TermSheet, TermSheetError

POLICY = DispatchPolicy("sonnet", 100_000)


def sheet(budget=800_000, paths=("rev.py",), extra=()):
    tasks = [Task("t1", "Create rev.py.", paths), *extra]
    checks = tuple(CheckSpec(f"c0{i}", "d", f"test_c0{i}.py", t.id) for i, t in enumerate(tasks, 1))
    return TermSheet("Reverse.", budget, (Round(1, budget, len(checks)),), checks, tuple(tasks))


def planned(s=None, *, tier="haiku", policy=POLICY, reads=None):
    return plan_dispatch(s or sheet(), tier=tier, profile=None, policy=policy, reads=reads or {})


def with_dispatch(s, **changes):
    [task] = s.tasks
    return dataclasses.replace(
        s,
        tasks=(dataclasses.replace(task, dispatch=dataclasses.replace(task.dispatch, **changes)),),
    )


# --- the route ---


def test_one_task_on_one_file_is_one_agent_and_two_files_are_the_firm():
    assert route_of(sheet()) == "one_agent"
    two = sheet(extra=(Task("t2", "Create up.py.", ("up.py",)),))
    assert route_of(two) == "firm"


def test_a_directory_or_the_whole_workspace_is_not_one_file():
    assert route_of(sheet(paths=("pkg",))) == "firm"
    assert route_of(sheet(paths=(".",))) == "firm"
    assert route_of(sheet(paths=("rev.py", "util.py"))) == "firm"


def test_tasks_that_all_write_the_same_single_file_are_one_agent():
    same = sheet(extra=(Task("t2", "Also rev.py.", ("./rev.py",)),))
    assert route_of(same) == "one_agent"


def test_the_route_is_shown_in_the_investors_words():
    assert route_text(sheet(), "one_agent") == "Route: one agent (one file, 1 check)"
    two = sheet(extra=(Task("t2", "Create up.py.", ("up.py",)),))
    assert route_text(two, "firm") == "Route: firm (2 tasks, files rev.py, up.py)"


def test_the_plan_sets_the_route_and_a_route_the_rule_would_not_pick_is_refused():
    s = planned()
    assert s.route == "one_agent" and dispatch.dispatch_problems(s, POLICY) == []
    two = planned(sheet(extra=(Task("t2", "Create up.py.", ("up.py",)),)))
    assert two.route == "firm"
    forced = dataclasses.replace(two, route="one_agent")
    [problem] = dispatch.dispatch_problems(forced, POLICY)
    assert "one file" in problem and "'firm'" in problem


def test_an_investor_may_set_a_one_file_sheet_to_the_firm():
    assert dispatch.dispatch_problems(dataclasses.replace(planned(), route="firm"), POLICY) == []


# --- the whitelist ---


def problems(s, policy=POLICY):
    return dispatch.dispatch_problems(s, policy)


@pytest.mark.parametrize(
    ("change", "text"),
    [
        ({"tier": "opus"}, "tier 'opus'"),
        ({"tier": "gpt-4"}, "tier 'gpt-4'"),
        ({"effort": "turbo"}, "effort 'turbo'"),
        ({"agent": "reviewer"}, "agent 'reviewer'"),
        ({"profile": "wizard"}, "profile 'wizard'"),
        ({"max_workers": 3}, "max_workers 3"),
        ({"max_workers": 0}, "max_workers 0"),
        ({"escalate_to": "opus"}, "escalate_to 'opus'"),
        ({"escalate_to": "gpt"}, "escalate_to 'gpt'"),
        ({"slice_micros": 4_999}, "slice_micros 4999"),
        ({"slice_micros": 100_001}, "slice_micros 100001"),
        ({"reads": ("t1",)}, "reads 't1'"),
        ({"reads": ("t9",)}, "reads 't9'"),
    ],
)
def test_a_value_outside_the_whitelist_is_refused(change, text):
    found = problems(with_dispatch(planned(), **change))
    assert any(text in p for p in found), found


def test_opus_is_allowed_only_with_max_tier_opus():
    s = with_dispatch(planned(), tier="opus", escalate_to="none")
    assert problems(s) != []
    assert problems(s, DispatchPolicy("opus", 100_000)) == []


def test_escalating_to_a_tier_below_the_task_is_refused():
    s = with_dispatch(planned(tier="sonnet"), escalate_to="haiku")
    assert any("below the task's own tier" in p for p in problems(s))


def test_a_tier_the_thinnest_round_cannot_fund_is_refused_before_spend():
    s = with_dispatch(planned(sheet(budget=250_000)), tier="sonnet")
    [p] = problems(s)
    assert "sonnet slice needs a round of at least $0.305" in p


def test_with_dispatch_off_a_sheet_that_carries_dispatch_or_a_route_is_refused():
    found = problems(planned(), None)
    assert any("task t1 carries dispatch" in p for p in found)
    assert any("carries a route" in p for p in found)
    assert problems(sheet(), None) == []


def test_with_dispatch_on_a_task_without_dispatch_or_a_route_is_refused():
    found = problems(sheet())
    assert any("route must be one of" in p for p in found)
    assert any("task t1 has no dispatch" in p for p in found)


def test_values_of_the_wrong_json_type_never_load():
    data = json.loads(planned().to_json())
    for key, bad in (
        ("effort", -1),
        ("max_workers", "2"),
        ("max_workers", True),
        ("tier", ["haiku"]),
        ("reads", "t2"),
    ):
        broken = json.loads(json.dumps(data))
        broken["tasks"][0]["dispatch"][key] = bad
        with pytest.raises(TermSheetError):
            TermSheet.from_json(json.dumps(broken))


def test_the_worker_cap_the_whitelist_allows_is_the_firms_own():
    assert max(dispatch.MAX_TASK_WORKERS) == firm.MAX_WORKERS_PER_TASK


# --- the plan ---


def test_the_plan_fills_every_task_with_the_run_tier_default_effort_and_a_step_up():
    d = planned().tasks[0].dispatch
    assert d == Dispatch("builder", None, "haiku", "default", "sonnet", 2, None, ())


def test_a_step_the_round_cannot_fund_is_planned_as_none_and_a_one_agent_run_keeps_one_worker():
    d = planned(sheet(budget=340_000)).tasks[0].dispatch
    assert d.escalate_to == "none" and d.max_workers == 1  # one agent route, nothing to step to
    two = planned(sheet(budget=340_000, extra=(Task("t2", "Create up.py.", ("up.py",)),)))
    assert all(t.dispatch.escalate_to == "none" and t.dispatch.max_workers == 2 for t in two.tasks)


def test_the_top_tier_can_only_step_its_effort():
    d = planned(tier="sonnet").tasks[0].dispatch
    assert d.escalate_to == "sonnet"
    assert (
        planned(tier="opus", policy=DispatchPolicy("opus", 100_000)).tasks[0].dispatch.tier
        == "opus"
    )


def test_reads_come_from_the_caller_and_are_kept():
    two = sheet(extra=(Task("t2", "Create up.py.", ("up.py",)),))
    s = planned(two, reads={"t2": ("t1",)})
    assert s.tasks[1].dispatch.reads == ("t1",) and s.tasks[0].dispatch.reads == ()


# --- the step up ---


def step(
    tier="haiku", effort="default", remaining=800_000, escalate_to="sonnet", max_tier="sonnet"
):
    return escalate(
        tier,
        effort,
        escalate_to=escalate_to,
        max_tier=max_tier,
        remaining_micros=remaining,
        slice_micros=100_000,
    )


def test_the_step_is_one_tier_up_when_the_round_can_fund_it():
    s = step()
    assert (s.tier, s.effort, s.changed, s.refused) == ("sonnet", "default", True, None)


def test_a_tier_that_does_not_fit_is_refused_with_the_reason_and_the_effort_steps_instead():
    s = step(remaining=340_000)
    assert (s.tier, s.effort, s.changed) == ("haiku", "high", True)
    assert s.refused == "sonnet needs $0.35 free in the round; $0.34 is left"


def test_the_top_tier_steps_its_effort_once_and_then_nothing():
    first = step(tier="sonnet", escalate_to="sonnet")
    assert (first.tier, first.effort, first.changed) == ("sonnet", "high", True)
    again = step(tier="sonnet", effort="high", escalate_to="sonnet")
    assert not again.changed and again.refused


def test_none_never_steps_and_a_ceiling_below_opus_is_kept():
    assert not step(escalate_to="none").changed
    capped = step(tier="sonnet", escalate_to="opus", max_tier="sonnet")
    assert capped.tier == "sonnet"  # --max-tier is a ceiling even if the sheet says opus


def fired(reason, *, one_agent=False, remaining=800_000, escalate_to="sonnet"):
    d = Dispatch("builder", None, "haiku", "default", escalate_to, 2, None, ())
    return replacement_hire(
        d,
        dispatch.first_hire(d),
        fired_for=reason,
        stalled_slices=2,
        max_tier="sonnet",
        remaining_micros=remaining,
        slice_micros=100_000,
        one_agent=one_agent,
    )


@pytest.mark.parametrize("reason", ["no progress", "slice limit"])
def test_only_the_gates_two_firings_step_a_worker_up(reason):
    hire = fired(reason)
    assert (hire.tier, hire.from_tier) == ("sonnet", "haiku")
    assert hire.why == f"predecessor fired: {reason}, 2 stalled slices"


@pytest.mark.parametrize(
    "reason", ["disputed", "blocked", "infrastructure: login", "worker said so"]
)
def test_no_other_reason_steps_a_worker_up(reason):
    hire = fired(reason)
    assert (hire.tier, hire.effort) == ("haiku", "default")
    assert hire.from_tier == "haiku" and hire.refused


def test_on_the_one_agent_route_a_replacement_that_is_not_stronger_is_not_hired():
    assert fired("no progress", one_agent=True) is not None
    assert fired("no progress", one_agent=True, escalate_to="none") is None
    assert fired("disputed", one_agent=True) is None


def test_a_hire_records_only_what_it_has():
    assert dispatch.first_hire(
        Dispatch("builder", None, "haiku", "off", "none", 1, None, ())
    ).data() == {
        "tier": "haiku",
        "effort": "off",
        "why": "term sheet",
    }
    assert set(fired("no progress", remaining=340_000).data()) == {
        "tier", "effort", "why", "from_tier", "refused",
    }  # fmt: skip


def test_the_cli_thinking_budget_of_each_effort():
    assert dispatch.thinking_for("off", 123) == 0
    assert dispatch.thinking_for("default", 123) == 123
    assert dispatch.thinking_for("default", None) is None
    assert dispatch.thinking_for("high", None) == dispatch.HIGH_THINKING_TOKENS


def test_tiers_are_found_in_aliases_and_full_ids_and_nothing_else():
    assert dispatch.tier_of("claude-sonnet-4-5-20250929") == "sonnet"
    assert dispatch.tier_of("haiku") == "haiku"
    assert dispatch.tier_of("gpt-4") is None


def test_the_worst_case_prices_the_slices_before_the_firing_and_one_at_the_new_price():
    # two haiku slices (cap $0.10 plus a $0.10 reserve) and one sonnet slice ($0.10 plus $0.30)
    assert dispatch.worst_case_micros(planned(), POLICY, 2) == 2 * 200_000 + 400_000
    off = with_dispatch(planned(), escalate_to="none", max_workers=1)
    assert dispatch.worst_case_micros(off, POLICY, 2) == 2 * 200_000


# --- what the investor reads ---

VIEW = DispatchView(POLICY, RunLevel("haiku", "off", 0, 1), 2, {"t1": 2_100})


def test_the_table_is_what_the_investor_reads():
    lines = dispatch.render_table(planned(), VIEW)
    assert lines == [
        "Route: one agent (one file, 1 check)",
        "",
        'DISPATCH (change it by editing "dispatch" in term_sheet.json, then choose [e]dit)',
        "task  agent    model  effort   if fired      context      slice cap",
        "t1    builder  haiku  default  sonnet, once  ~2.1k chars  $0.10",
        "Run level: draft haiku | review off | held-out off | parallel 1",
        "Worst case if every task steps up: $0.80 of $0.80 (2 slices, then one at the new price)",
    ]


def test_the_table_says_why_a_step_is_missing_and_when_the_worst_case_is_over_the_budget():
    off = with_dispatch(planned(), escalate_to="none", max_workers=1)
    assert "none (one agent)" in "\n".join(dispatch.render_table(off, VIEW))
    twice = planned(sheet(budget=340_000, extra=(Task("t2", "Create up.py.", ("up.py",)),)))
    text = "\n".join(dispatch.render_table(twice, VIEW))
    assert "stays haiku (a round of $0.35 would allow sonnet)" in text
    assert "OVER the budget" in text


# --- the term sheet that carries it ---


def test_a_sheet_without_dispatch_hashes_exactly_as_it_always_did(tmp_path):
    old = TermSheet(
        "Reverse a string.",
        500_000,
        (Round(1, 500_000, 2),),
        (
            CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
            CheckSpec("c02", "empty string", "test_c02.py", "t1"),
        ),
        (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
    )
    for name in ("test_c01.py", "test_c02.py"):
        (tmp_path / name).write_text("def test_x():\n    pass\n")
    # sha256 of the JSON that `TermSheet.to_json` wrote before dispatch existed (origin/main)
    assert content_hashes(old, tmp_path)["term_sheet"] == (
        "aa0ce180f53592efa47a651dc9e0b62d750b5817cec5f2dce48f585f158c7f5b"
    )
    assert "dispatch" not in old.to_json() and "route" not in old.to_json()


def test_a_sheet_with_dispatch_round_trips_and_hashes_differently(tmp_path):
    s = planned()
    assert TermSheet.from_json(s.to_json()) == s
    (tmp_path / "test_c01.py").write_text("def test_x():\n    pass\n")
    plain = dataclasses.replace(
        s, route=None, tasks=(dataclasses.replace(s.tasks[0], dispatch=None),)
    )
    assert content_hashes(s, tmp_path) != content_hashes(plain, tmp_path)
    assert (
        hashlib.sha256(s.to_json().encode()).hexdigest()
        == content_hashes(s, tmp_path)["term_sheet"]
    )
