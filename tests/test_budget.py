import random

import pytest

from boss.budget import (
    MIN_SLICE_MICROS,
    RESERVE_MICROS,
    is_top_up,
    min_round_budget,
    next_slice_cap,
    plan_rounds,
    remaining,
    reserve_for,
    round_budget,
    round_spend,
    unlocked,
)
from boss.ledger import Event, EventType
from boss.termsheet import CheckSpec, Round, Task, TermSheet, _money_problems, _round_problems


def sheet(rounds: tuple[Round, ...] | None = None, n_checks: int = 4) -> TermSheet:
    rounds = rounds or (Round(1, 600_000, 2), Round(2, 400_000, n_checks))
    return TermSheet(
        idea="x",
        budget_micros=sum(r.budget_micros for r in rounds),
        rounds=rounds,
        checks=tuple(CheckSpec(f"c{i}", "d", f"test_c{i}.py", "t1") for i in range(n_checks)),
        tasks=(Task("t1", "b", (".",)),),
    )


def ev(
    round_n: int = 1,
    kind: EventType = EventType.SLICE_END,
    cost: int | None = 0,
    **data: object,
) -> Event:
    return Event(
        run="r", round=round_n, actor="worker:a", event=kind, cost_micros=cost, data=dict(data)
    )


def top_up(micros: object, round_n: int = 1, actor: str = "investor") -> Event:
    return Event(
        run="r", round=round_n, actor=actor, event=EventType.TOPPED_UP, data={"micros": micros}
    )


def test_a_top_up_of_one_micro_is_accepted() -> None:
    assert round_budget(sheet(), [top_up(1)], 1) == 600_001


def test_round_budget_is_sheet_amount_without_events() -> None:
    assert round_budget(sheet(), [], 1) == 600_000
    assert round_budget(sheet(), [], 2) == 400_000


def test_round_budget_adds_top_ups_of_that_round_only() -> None:
    events = [top_up(50_000), top_up(25_000), top_up(999_000, round_n=2), ev(1, cost=7)]
    assert round_budget(sheet(), events, 1) == 675_000
    assert round_budget(sheet(), events, 2) == 1_399_000


@pytest.mark.parametrize("actor", ["worker:a", "boss", "gate", "rule", "role:critic"])
def test_only_the_investors_top_up_counts(actor: str) -> None:
    events = [top_up(50_000, actor=actor)]
    assert round_budget(sheet(), events, 1) == 600_000
    assert remaining(sheet(), events, 1) == 600_000
    assert not is_top_up(events[0])
    assert is_top_up(top_up(1))


def test_remaining_counts_an_investor_top_up() -> None:
    spent = ev(1, cost=590_000)
    assert remaining(sheet(), [spent], 1) == 10_000
    assert remaining(sheet(), [spent, top_up(200_000)], 1) == 210_000


@pytest.mark.parametrize("bad", [0, -5, 1.5, "10", True, None])
def test_round_budget_rejects_malformed_top_up(bad: object) -> None:
    with pytest.raises(ValueError, match="topped_up"):
        round_budget(sheet(), [top_up(bad)], 1)


def test_round_budget_missing_round_raises() -> None:
    with pytest.raises(ValueError, match="round 3"):
        round_budget(sheet(), [], 3)


def test_round_spend_sums_one_round_across_actors() -> None:
    boss = Event(run="r", round=1, actor="boss", event=EventType.BOSS_CALL, cost_micros=4_000)
    events = [ev(1, cost=10_000), ev(1, cost=2_500), boss, ev(2, cost=90_000)]
    spend = round_spend(events, 1)
    assert (spend.cost_micros, spend.events) == (16_500, 3)
    assert round_spend(events, 3).cost_micros == 0


def test_remaining_subtracts_spend_and_counts_top_ups() -> None:
    events = [ev(1, cost=100_000), ev(1, cost=50_000), top_up(30_000), ev(2, cost=1_000)]
    assert remaining(sheet(), events, 1) == 600_000 + 30_000 - 150_000
    assert remaining(sheet(), events, 2) == 399_000


def start(n: int, cap: object, round_n: int = 1) -> Event:
    return ev(round_n, EventType.SLICE_START, slice=n, cap_micros=cap)


def end(n: int, cost: int | None, outcome: str = "crashed", round_n: int = 1) -> Event:
    return ev(round_n, cost=cost, slice=n, outcome=outcome)


def test_a_slice_of_unknown_cost_is_charged_at_its_cap() -> None:
    events = [start(1, 40_000), end(1, 100_000), start(2, 30_000), end(2, None)]
    assert remaining(sheet(), events, 1) == 600_000 - 100_000 - 30_000
    spend = round_spend(events, 1)  # the ledger's own total still says "unknown", not 30,000
    assert (spend.cost_micros, spend.unknown_cost_events) == (100_000, 1)


def test_unknown_cost_slices_cannot_be_funded_without_end() -> None:
    # Found by the threat model: four crashed slices were funded against a $0.12 round, because
    # an unknown cost left the round's remaining budget untouched.
    events: list[Event] = []
    funded = 0
    while (cap := next_slice_cap(remaining(sheet(), events, 1), slice_micros=200_000)) is not None:
        funded += 1
        events += [start(funded, cap), end(funded, None)]
    assert (
        funded == 3
    )  # 600,000: caps of 200,000, 200,000 and 100,000, then only the reserve is left
    assert remaining(sheet(), events, 1) == 100_000


@pytest.mark.parametrize("outcome", ["login", "rate_limited", "usage_limit", "api_error"])
def test_an_infrastructure_failure_of_unknown_cost_is_not_charged(outcome: str) -> None:
    events = [start(1, 40_000), end(1, None, outcome)]
    assert remaining(sheet(), events, 1) == 600_000


@pytest.mark.parametrize("outcome", ["crashed", "timeout", "completed", "capped", None])
def test_any_other_slice_of_unknown_cost_is_charged(outcome: str | None) -> None:
    events = [
        start(1, 40_000),
        ev(1, cost=None, slice=1, **({"outcome": outcome} if outcome else {})),
    ]
    assert remaining(sheet(), events, 1) == 560_000


def test_unknown_cost_charges_match_each_slice_to_its_own_start() -> None:
    other = Event(
        run="r",
        round=1,
        actor="worker:b",
        event=EventType.SLICE_START,
        data={"slice": 1, "cap_micros": 90_000},
    )
    events = [
        start(1, 40_000),
        other,  # another worker's slice 1, never ended: its own lost slice
        end(1, None),
        start(2, 70_000, round_n=2),
        end(2, None, round_n=2),  # another round
        end(9, None),  # no recorded start: nothing to charge
        start(3, "lots"),
        end(3, None),  # malformed cap: nothing to charge
        start(4, 25_000),
        end(4, 0),  # a known cost of zero is not unknown
    ]
    assert remaining(sheet(), events, 1) == 600_000 - 40_000 - 90_000
    assert remaining(sheet(), events, 2) == 400_000 - 70_000


def test_a_slice_cap_of_one_micro_is_charged() -> None:
    assert remaining(sheet(), [start(1, 1)], 1) == 600_000 - 1


def test_an_end_closes_only_the_slice_it_names() -> None:
    # Slice 2 never reports a cost; slice 1 ends later with one. Only slice 2 is charged.
    events = [start(1, 40_000), start(2, 70_000), end(2, None), end(1, 5)]
    assert remaining(sheet(), events, 1) == 600_000 - 5 - 70_000


def test_a_slice_that_started_and_never_ended_is_charged_at_its_cap() -> None:
    # The run was interrupted mid-slice: what it spent was never reported.
    assert remaining(sheet(), [start(1, 40_000)], 1) == 560_000
    assert remaining(sheet(), [start(1, 40_000), end(1, 12_000)], 1) == 588_000


def test_a_lost_slice_is_still_charged_after_the_same_slice_number_runs_again() -> None:
    events = [start(1, 40_000), start(1, 30_000), end(1, 10_000)]
    assert remaining(sheet(), events, 1) == 600_000 - 40_000 - 10_000
    twice_lost = [start(1, 40_000), start(1, 30_000)]
    assert remaining(sheet(), twice_lost, 1) == 600_000 - 40_000 - 30_000


def test_a_failed_infrastructure_attempt_is_not_charged_when_the_slice_runs_again() -> None:
    events = [start(1, 40_000), end(1, None, "rate_limited"), start(1, 40_000), end(1, 9_000)]
    assert remaining(sheet(), events, 1) == 600_000 - 9_000


def s_start(n: int, cap: int, session: str, round_n: int = 1) -> Event:
    return ev(round_n, EventType.SLICE_START, slice=n, cap_micros=cap, session=session)


def s_end(
    n: int, cost: int | None, total: int | None, outcome: str = "completed", round_n: int = 1
) -> Event:
    return ev(round_n, cost=cost, slice=n, outcome=outcome, session_total_micros=total)


def test_a_lost_slice_is_counted_once_when_its_session_is_resumed() -> None:
    # Slice 2 spent 30,000 before the run was interrupted; nothing was booked for it. Slice 3
    # resumes the session and the CLI reports the cumulative 70,000: slice 3 books 70,000 - 30,000.
    events = [
        s_start(1, 40_000, "S"),
        s_end(1, 30_000, 30_000),
        s_start(2, 40_000, "S"),  # lost
        s_start(3, 40_000, "S"),
        s_end(3, 40_000, 70_000),
    ]
    assert round_spend(events, 1).cost_micros == 70_000  # the session's real total
    assert remaining(sheet(), events, 1) == 600_000 - 70_000  # not another 40,000 for slice 2


def test_a_lost_slice_stays_charged_until_a_later_slice_of_its_session_reports() -> None:
    lost = [s_start(1, 40_000, "S"), s_end(1, 30_000, 30_000), s_start(2, 40_000, "S")]
    assert remaining(sheet(), lost, 1) == 600_000 - 30_000 - 40_000
    # Slice 3 of the same session is lost too (cost unknown): nothing has covered slice 2 yet.
    both = [*lost, s_start(3, 25_000, "S"), s_end(3, None, None, "timeout")]
    assert remaining(sheet(), both, 1) == 600_000 - 30_000 - 40_000 - 25_000
    # Slice 4 reports the session's total, which holds the spend of slices 2 and 3.
    covered = [*both, s_start(4, 40_000, "S"), s_end(4, 55_000, 85_000)]
    assert remaining(sheet(), covered, 1) == 600_000 - 85_000


def test_the_same_slice_started_again_in_its_session_is_counted_once() -> None:
    events = [
        s_start(1, 40_000, "S"),
        s_end(1, 30_000, 30_000),
        s_start(2, 40_000, "S"),  # interrupted
        s_start(2, 40_000, "S"),  # run again after a resume of the run
        s_end(2, 35_000, 65_000),
    ]
    assert remaining(sheet(), events, 1) == 600_000 - 65_000


def test_a_report_from_another_session_does_not_cover_a_lost_slice() -> None:
    events = [
        s_start(1, 40_000, "S"),  # lost before the CLI reported anything: S is never resumed
        s_start(1, 40_000, "S2"),  # a new session, so no cumulative total includes slice 1
        s_end(1, 30_000, 30_000),
    ]
    assert remaining(sheet(), events, 1) == 600_000 - 30_000 - 40_000


def test_a_report_without_a_total_does_not_cover_a_lost_slice() -> None:
    events = [
        s_start(1, 40_000, "S"),
        s_end(1, 30_000, 30_000),
        s_start(2, 40_000, "S"),  # lost
        s_start(3, 40_000, "S"),
        s_end(3, 10_000, None),  # no session total: it cannot be known to include slice 2
    ]
    assert remaining(sheet(), events, 1) == 600_000 - 30_000 - 40_000 - 10_000


def test_a_lost_slice_covered_in_a_later_round_is_not_charged_in_its_own() -> None:
    events = [
        s_start(1, 40_000, "S", round_n=1),
        s_end(1, 30_000, 30_000, round_n=1),
        s_start(2, 40_000, "S", round_n=1),  # lost when round 1 ended
        s_start(3, 40_000, "S", round_n=2),
        s_end(3, 40_000, 70_000, round_n=2),  # books slice 2's spend as well, in round 2
    ]
    assert remaining(sheet(), events, 1) == 600_000 - 30_000
    assert remaining(sheet(), events, 2) == 400_000 - 40_000
    assert round_spend(events, 1).cost_micros + round_spend(events, 2).cost_micros == 70_000


def test_a_lost_slice_of_another_worker_is_not_covered_by_this_workers_session() -> None:
    other = Event(
        run="r",
        round=1,
        actor="worker:b",
        event=EventType.SLICE_START,
        data={"slice": 1, "cap_micros": 90_000, "session": "T"},
    )
    events = [other, s_start(1, 40_000, "S"), s_end(1, 30_000, 30_000)]
    assert remaining(sheet(), events, 1) == 600_000 - 30_000 - 90_000


@pytest.mark.parametrize(
    ("model", "micros"),
    [
        ("haiku", RESERVE_MICROS),
        ("sonnet", 3 * RESERVE_MICROS),
        ("opus", 5 * RESERVE_MICROS),
        ("claude-haiku-4-5", RESERVE_MICROS),
        ("claude-sonnet-4-5-20250929", 3 * RESERVE_MICROS),
        ("Opus[1m]", 5 * RESERVE_MICROS),
        ("", RESERVE_MICROS),
        ("gpt-x", RESERVE_MICROS),  # an unknown model keeps the one figure there has always been
    ],
)
def test_the_reserve_is_per_model_family_and_unknown_models_keep_the_default(
    model: str, micros: int
) -> None:
    assert reserve_for(model) == micros


def test_a_larger_model_needs_a_larger_round_to_fund_one_slice() -> None:
    assert min_round_budget(reserve_for("haiku")) < min_round_budget(reserve_for("sonnet"))
    assert min_round_budget(reserve_for("sonnet")) < min_round_budget(reserve_for("opus"))


def test_remaining_negative_after_overshoot() -> None:
    assert remaining(sheet(), [ev(1, cost=450_000), ev(1, cost=200_000)], 1) == -50_000


def test_remaining_missing_round_raises() -> None:
    with pytest.raises(ValueError):
        remaining(sheet(), [], 9)


def test_defaults() -> None:
    # Measured on Haiku: a slice capped at $0.030 spent $0.099, so one response is about $0.10.
    assert RESERVE_MICROS == 100_000
    assert MIN_SLICE_MICROS == 5_000


def test_cap_is_the_slice_when_plenty_remains() -> None:
    assert next_slice_cap(1_000_000, slice_micros=40_000) == 40_000
    assert next_slice_cap(10**12, slice_micros=40_000, reserve_micros=0) == 40_000


def test_cap_boundary_where_the_slice_just_fits_above_the_reserve() -> None:
    assert next_slice_cap(140_000, slice_micros=40_000) == 40_000
    assert next_slice_cap(139_999, slice_micros=40_000) == 39_999


def test_cap_shrinks_to_what_is_left_above_the_reserve() -> None:
    assert next_slice_cap(120_000, slice_micros=40_000) == 20_000


def test_cap_boundary_at_min_cap() -> None:
    assert next_slice_cap(105_000, slice_micros=40_000) == 5_000
    assert next_slice_cap(104_999, slice_micros=40_000) is None


def test_no_slice_is_funded_out_of_the_reserve() -> None:
    assert next_slice_cap(100_000, slice_micros=40_000) is None
    assert next_slice_cap(0, slice_micros=40_000) is None
    assert next_slice_cap(-50_000, slice_micros=40_000) is None


def test_reserve_zero_uses_all_that_remains() -> None:
    assert next_slice_cap(12_345, slice_micros=40_000, reserve_micros=0) == 12_345
    assert next_slice_cap(4_999, slice_micros=40_000, reserve_micros=0) is None


def test_custom_reserve_and_min_cap() -> None:
    assert next_slice_cap(9_000, slice_micros=40_000, reserve_micros=7_000, min_cap=2_000) == 2_000
    assert next_slice_cap(8_999, slice_micros=40_000, reserve_micros=7_000, min_cap=2_000) is None


def test_negative_reserve_is_rejected() -> None:
    with pytest.raises(ValueError, match="reserve_micros"):
        next_slice_cap(10_000, slice_micros=5_000, reserve_micros=-1)


def test_min_round_budget_is_the_smallest_budget_that_funds_a_slice() -> None:
    assert min_round_budget() == 105_000
    assert next_slice_cap(min_round_budget(), slice_micros=40_000) == MIN_SLICE_MICROS
    assert next_slice_cap(min_round_budget() - 1, slice_micros=40_000) is None
    smallest = min_round_budget(30_000, min_cap=1_000)
    assert smallest == 31_000
    assert next_slice_cap(smallest, slice_micros=9_000, reserve_micros=30_000, min_cap=1_000)


def test_a_round_never_exceeds_its_budget_when_each_overshoot_fits_the_reserve() -> None:
    # The property the reserve exists for. Every slice spends its cap plus an overshoot of up to
    # one reserve (the worst case: the CLI notices the cap one response late, every time).
    rng = random.Random(20260930)
    for _ in range(2_000):
        budget = rng.randrange(1, 2_000_000)
        slice_micros = rng.randrange(5_000, 400_000)
        reserve = rng.randrange(0, 200_000)
        spent = 0
        while (
            cap := next_slice_cap(budget - spent, slice_micros=slice_micros, reserve_micros=reserve)
        ) is not None:
            assert MIN_SLICE_MICROS <= cap <= slice_micros
            spent += cap + rng.choice((0, reserve, rng.randrange(0, reserve + 1)))
            assert spent <= budget
        assert budget - spent < reserve + MIN_SLICE_MICROS  # it stopped only when it had to


def test_a_percentage_headroom_would_not_have_held_the_budget() -> None:
    # The rule this replaced: cap = remaining / 1.25. With the measured one-response overshoot
    # ($0.069 over a $0.030 cap) it breaks the budget; the fixed reserve does not.
    budget, overshoot = 40_000, 69_000
    old_cap = int(budget / 1.25)
    assert old_cap + overshoot > budget
    assert next_slice_cap(budget, slice_micros=30_000) is None  # too small to fund safely


def test_unlocked_thresholds() -> None:
    s = sheet()
    assert not unlocked(s, 1, 1)
    assert unlocked(s, 1, 2)
    assert unlocked(s, 1, 4)
    assert not unlocked(s, 2, 3)
    assert unlocked(s, 2, 4)


def test_a_threshold_cannot_ask_for_more_checks_than_the_investor_left_required() -> None:
    # Round 2 of this sheet unlocks at 4 checks. After the investor drops one, 3 remain.
    assert not unlocked(sheet(), 2, 3)
    assert unlocked(sheet(), 2, 3, total_checks=3)
    assert not unlocked(sheet(), 2, 2, total_checks=3)
    assert unlocked(sheet(), 1, 2, total_checks=4) and not unlocked(sheet(), 1, 1, total_checks=4)


def test_unlocked_missing_round_raises() -> None:
    with pytest.raises(ValueError):
        unlocked(sheet(), 5, 1)


def test_plan_1m_8_checks_3_rounds() -> None:
    assert plan_rounds(1_000_000, 8, 3) == (
        Round(1, 333_334, 3),
        Round(2, 333_333, 6),
        Round(3, 333_333, 8),
    )


def test_plan_remainder_goes_to_earliest_rounds() -> None:
    assert plan_rounds(100, 7, 3) == (Round(1, 34, 3), Round(2, 33, 5), Round(3, 33, 7))
    assert plan_rounds(101, 7, 3) == (Round(1, 34, 3), Round(2, 34, 5), Round(3, 33, 7))


def test_plan_fewer_checks_than_rounds_uses_one_round_per_check() -> None:
    assert plan_rounds(1_000, 2, 3) == (Round(1, 500, 1), Round(2, 500, 2))


def test_plan_single_check_is_one_round() -> None:
    assert plan_rounds(777, 1, 3) == (Round(1, 777, 1),)


def test_plan_default_is_three_rounds() -> None:
    assert len(plan_rounds(900, 9)) == 3


def test_plan_budget_equal_to_round_count() -> None:
    assert plan_rounds(3, 9, 3) == (Round(1, 1, 3), Round(2, 1, 6), Round(3, 1, 9))


@pytest.mark.parametrize(
    ("budget", "n_checks", "n_rounds"),
    [(0, 5, 3), (-1, 5, 3), (100, 0, 3), (100, -2, 3), (100, 5, 0), (100, 5, -1)],
)
def test_plan_non_positive_inputs_raise(budget: int, n_checks: int, n_rounds: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        plan_rounds(budget, n_checks, n_rounds)


def test_plan_non_positive_inputs_say_which_inputs_must_be_positive() -> None:
    with pytest.raises(ValueError, match="budget_micros, n_checks and n_rounds must be positive"):
        plan_rounds(0, 8)


def test_plan_budget_below_round_count_raises() -> None:
    with pytest.raises(ValueError, match="cannot fund"):
        plan_rounds(2, 9, 3)


def test_plan_min_round_drops_rounds_from_the_end_until_each_can_fund_a_slice() -> None:
    assert plan_rounds(900, 9, 3, min_round_micros=300) == plan_rounds(900, 9, 3)
    assert plan_rounds(899, 9, 3, min_round_micros=300) == plan_rounds(899, 9, 2)
    assert plan_rounds(599, 9, 3, min_round_micros=300) == (Round(1, 599, 9),)
    assert plan_rounds(10, 9, 3, min_round_micros=300) == (Round(1, 10, 9),)  # one round: all of it


def test_plan_min_round_defaults_to_no_floor() -> None:
    assert plan_rounds(100, 7, 3, min_round_micros=0) == plan_rounds(100, 7, 3)
    assert plan_rounds(3, 9, 3) == (Round(1, 1, 3), Round(2, 1, 6), Round(3, 1, 9))


def test_plan_small_budget_still_ok_when_fewer_rounds_are_used() -> None:
    assert plan_rounds(2, 2, 5) == (Round(1, 1, 1), Round(2, 1, 2))


def test_plan_properties_and_term_sheet_validity() -> None:
    planned = 0
    for budget in (1, 2, 3, 7, 100, 999_999, 1_000_000, 1_234_567):
        for n_checks in range(1, 13):
            for n_rounds in range(1, 7):
                rounds_used = min(n_rounds, n_checks)
                if budget < rounds_used:
                    with pytest.raises(ValueError):
                        plan_rounds(budget, n_checks, n_rounds)
                    continue
                planned += 1
                plan = plan_rounds(budget, n_checks, n_rounds)
                budgets = [r.budget_micros for r in plan]
                unlocks = [r.unlock_checks for r in plan]
                assert len(plan) == rounds_used
                assert sum(budgets) == budget
                assert min(budgets) >= 1
                assert budgets == sorted(budgets, reverse=True)
                assert max(budgets) - min(budgets) <= 1
                assert unlocks == sorted(unlocks)
                assert all(1 <= u <= n_checks for u in unlocks)
                assert unlocks[-1] == n_checks
                s = sheet(plan, n_checks=n_checks)
                assert _round_problems(s) == []
                assert _money_problems(s) == []
    assert planned > 300


def role_call(cost: int | None, outcome: str = "timeout", cap: object = 150_000, round_n: int = 1):
    data = {"outcome": outcome} | ({} if cap is None else {"cap_micros": cap})
    return Event(
        run="r", round=round_n, actor="role:examiner", event=EventType.ROLE_CALL,
        cost_micros=cost, data=data,
    )  # fmt: skip


def test_a_timed_out_role_call_is_charged_at_its_cap_so_the_round_cannot_spend_it_twice() -> None:
    full = remaining(sheet(), [], 1)
    assert remaining(sheet(), [role_call(None)], 1) == full - 150_000
    assert round_spend([role_call(None)], 1).unknown_cost_events == 1  # reported as unknown


def test_a_role_call_that_was_not_charged_is_not_charged_here() -> None:
    full = remaining(sheet(), [], 1)
    assert remaining(sheet(), [role_call(0, "skipped")], 1) == full
    assert remaining(sheet(), [role_call(None, "login")], 1) == full  # infrastructure: no work
    assert remaining(sheet(), [role_call(None, cap=None)], 1) == full  # a ledger from before caps
    assert remaining(sheet(), [role_call(None, round_n=2)], 1) == full  # another round's


def test_timed_out_role_calls_cannot_fund_slices_past_the_round_budget() -> None:
    events = [role_call(None), role_call(None), role_call(None)]
    spent = 0
    while (cap := next_slice_cap(remaining(sheet(), events, 1), slice_micros=200_000)) is not None:
        events.append(start(len(events), cap))
        events.append(end(len(events) - 1, cap, "completed"))
        spent += cap
    assert spent + 3 * 150_000 <= round_budget(sheet(), events, 1)
