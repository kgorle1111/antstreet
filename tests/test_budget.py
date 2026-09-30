import pytest

from boss.budget import (
    HEADROOM,
    MIN_SLICE_MICROS,
    next_slice_cap,
    plan_rounds,
    remaining,
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


def top_up(micros: object, round_n: int = 1) -> Event:
    return ev(round_n, EventType.TOPPED_UP, micros=micros)


def test_round_budget_is_sheet_amount_without_events() -> None:
    assert round_budget(sheet(), [], 1) == 600_000
    assert round_budget(sheet(), [], 2) == 400_000


def test_round_budget_adds_top_ups_of_that_round_only() -> None:
    events = [top_up(50_000), top_up(25_000), top_up(999_000, round_n=2), ev(1, cost=7)]
    assert round_budget(sheet(), events, 1) == 675_000
    assert round_budget(sheet(), events, 2) == 1_399_000


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


def test_unknown_cost_does_not_reduce_remaining_but_is_counted() -> None:
    events = [ev(1, cost=100_000), ev(1, cost=None), ev(1, cost=None)]
    assert remaining(sheet(), events, 1) == 500_000
    spend = round_spend(events, 1)
    assert (spend.cost_micros, spend.unknown_cost_events) == (100_000, 2)


def test_remaining_negative_after_overshoot() -> None:
    assert remaining(sheet(), [ev(1, cost=450_000), ev(1, cost=200_000)], 1) == -50_000


def test_remaining_missing_round_raises() -> None:
    with pytest.raises(ValueError):
        remaining(sheet(), [], 9)


def test_defaults() -> None:
    assert HEADROOM == 0.25
    assert MIN_SLICE_MICROS == 5_000


def test_cap_is_slice_when_plenty_remains() -> None:
    assert next_slice_cap(1_000_000, slice_micros=40_000) == 40_000


def test_cap_exactly_fitting_the_slice() -> None:
    assert next_slice_cap(50_000, slice_micros=40_000) == 40_000  # 40_000 * 1.25 == 50_000


def test_cap_one_micro_short_of_fitting_the_slice() -> None:
    assert next_slice_cap(49_999, slice_micros=40_000) == 39_999  # 39_999 * 1.25 = 49_998.75


def test_cap_shrinks_to_what_remaining_allows() -> None:
    assert next_slice_cap(20_000, slice_micros=40_000) == 16_000


def test_cap_never_exceeds_the_slice() -> None:
    assert next_slice_cap(10**12, slice_micros=40_000) == 40_000
    assert next_slice_cap(10**12, slice_micros=40_000, headroom=0.0) == 40_000


def test_cap_boundary_at_min_cap() -> None:
    assert next_slice_cap(6_250, slice_micros=40_000) == 5_000  # 5_000 * 1.25 == 6_250
    assert next_slice_cap(6_249, slice_micros=40_000) is None  # cap would be 4_999


def test_cap_none_below_min_cap_times_headroom() -> None:
    assert next_slice_cap(6_000, slice_micros=40_000) is None
    assert next_slice_cap(0, slice_micros=40_000) is None


def test_cap_none_when_overshot() -> None:
    assert next_slice_cap(-50_000, slice_micros=40_000) is None


def test_cap_headroom_zero_uses_all_remaining() -> None:
    assert next_slice_cap(12_345, slice_micros=40_000, headroom=0.0) == 12_345
    assert next_slice_cap(4_999, slice_micros=40_000, headroom=0.0) is None


def test_cap_custom_headroom_and_min_cap() -> None:
    assert next_slice_cap(3_000, slice_micros=40_000, headroom=0.5, min_cap=2_000) == 2_000
    assert next_slice_cap(2_999, slice_micros=40_000, headroom=0.5, min_cap=2_000) is None


def test_cap_negative_headroom_rejected() -> None:
    with pytest.raises(ValueError, match="headroom"):
        next_slice_cap(10_000, slice_micros=5_000, headroom=-0.1)


def test_cap_is_the_largest_that_fits() -> None:
    for remaining_micros in range(6_250, 50_000, 37):
        cap = next_slice_cap(remaining_micros, slice_micros=40_000)
        assert cap is not None
        assert cap * 1.25 <= remaining_micros < (cap + 1) * 1.25


def test_unlocked_thresholds() -> None:
    s = sheet()
    assert not unlocked(s, 1, 1)
    assert unlocked(s, 1, 2)
    assert unlocked(s, 1, 4)
    assert not unlocked(s, 2, 3)
    assert unlocked(s, 2, 4)


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


def test_plan_budget_below_round_count_raises() -> None:
    with pytest.raises(ValueError, match="cannot fund"):
        plan_rounds(2, 9, 3)


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
