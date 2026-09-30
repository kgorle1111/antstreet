import random
from collections.abc import Sequence

import pytest

from boss.ledger import Event, EventType
from boss.limits import RunLimits, breach, spend_ceiling


def ev(
    kind: EventType = EventType.SLICE_END,
    round_n: int = 1,
    cost: int | None = 0,
) -> Event:
    return Event(run="r", round=round_n, actor="boss", event=kind, cost_micros=cost)


def slices(n: int) -> list[Event]:
    return [ev(EventType.SLICE_START) for _ in range(n)]


def hires(n: int) -> list[Event]:
    return [ev(EventType.HIRED) for _ in range(n)]


DEFAULT = RunLimits()


def check(
    events: Sequence[Event] = (),
    limits: RunLimits = DEFAULT,
    ceiling: int = 1_000_000,
    elapsed: float = 0.0,
) -> str | None:
    return breach(events, limits, ceiling_micros=ceiling, elapsed_s=elapsed)


def test_defaults() -> None:
    assert RunLimits() == RunLimits(max_slices=60, max_workers=16, max_seconds=None)


@pytest.mark.parametrize("field", ["max_slices", "max_workers"])
@pytest.mark.parametrize("bad", [0, -1, True, False, 1.0, "3", None])
def test_counts_must_be_ints_of_at_least_one(field: str, bad: object) -> None:
    with pytest.raises(ValueError, match=field):
        RunLimits(**{field: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, 0.0, -1, -0.5, True, False, "5", float("nan")])
def test_max_seconds_must_be_none_or_positive_number(bad: object) -> None:
    with pytest.raises(ValueError, match="max_seconds"):
        RunLimits(max_seconds=bad)  # type: ignore[arg-type]


def test_smallest_valid_limits_are_accepted() -> None:
    limits = RunLimits(max_slices=1, max_workers=1, max_seconds=0.001)
    assert (limits.max_slices, limits.max_workers, limits.max_seconds) == (1, 1, 0.001)
    assert RunLimits(max_seconds=30).max_seconds == 30


def test_spend_ceiling_is_budgets_plus_one_reserve_per_round() -> None:
    assert spend_ceiling([600_000, 400_000], 100_000) == 1_200_000
    assert spend_ceiling([500_000], 0) == 500_000
    assert spend_ceiling([1, 2, 3], 10) == 36


def test_spend_ceiling_rejects_negative_reserve_and_empty_budgets() -> None:
    with pytest.raises(ValueError, match="reserve_micros"):
        spend_ceiling([1], -1)
    with pytest.raises(ValueError, match="round_budgets_micros"):
        spend_ceiling([], 100)


def test_empty_ledger_is_inside_every_limit() -> None:
    limits = RunLimits(max_slices=1, max_workers=1, max_seconds=1)
    assert check([], limits, ceiling=0, elapsed=0.0) is None


def test_spend_boundary_equal_is_inside_one_over_is_a_breach() -> None:
    assert check([ev(cost=1_000_000)]) is None
    assert check([ev(cost=1_000_000), ev(cost=1)]) == (
        "spend $1.000001 is over the run ceiling of $1"
    )


def test_spend_sums_across_rounds_and_actors() -> None:
    assert check([ev(round_n=1, cost=600_000), ev(round_n=2, cost=400_000)]) is None
    assert check([ev(round_n=1, cost=600_000), ev(round_n=2, cost=400_001)]) is not None


def test_round_zero_spend_is_excluded() -> None:
    boss = ev(EventType.BOSS_CALL, round_n=0, cost=9_000_000)
    assert check([boss]) is None
    assert check([boss, ev(round_n=1, cost=1_000_001)]) is not None
    assert check([boss, ev(round_n=1, cost=1_000_000)]) is None


def test_round_one_is_the_first_counted_round() -> None:
    assert check([ev(round_n=1, cost=1_000_001)]) is not None


def test_unknown_cost_adds_nothing() -> None:
    events = [ev(cost=None) for _ in range(50)] + [ev(cost=1_000_000)]
    assert check(events) is None
    assert check([ev(cost=None)], ceiling=0) is None
    assert check([ev(cost=1)], ceiling=0) is not None


def test_slices_boundary_the_limit_th_start_stops_the_run() -> None:
    limits = RunLimits(max_slices=3)
    assert check(slices(2), limits) is None
    assert check(slices(3), limits) == "3 slices started; the run limit is 3"
    assert check(slices(4), limits) is not None


def test_only_slice_start_counts_as_a_slice() -> None:
    limits = RunLimits(max_slices=2)
    other = [ev(EventType.SLICE_END), ev(EventType.CHECK_RESULT), ev(EventType.HIRED)]
    assert check(other + slices(1), limits) is None


def test_workers_boundary_the_limit_is_allowed_one_more_is_not() -> None:
    limits = RunLimits(max_workers=2)
    assert check(hires(1), limits) is None
    assert check(hires(2), limits) is None
    assert check(hires(3), limits) == "3 workers hired; the run limit is 2"


def test_only_hired_counts_as_a_worker() -> None:
    limits = RunLimits(max_workers=1)
    fired = [ev(EventType.HIRED), ev(EventType.FIRED), ev(EventType.REASSIGNED)]
    assert check(fired, limits) is None


def test_clock_boundary_reaching_the_limit_stops_the_run() -> None:
    limits = RunLimits(max_seconds=60)
    assert check(limits=limits, elapsed=59.999) is None
    assert check(limits=limits, elapsed=60.0) == "60s of wall clock elapsed; the run limit is 60s"
    assert check(limits=limits, elapsed=61.0) is not None


def test_no_clock_limit_means_any_elapsed_time_is_fine() -> None:
    assert check(elapsed=10.0**9) is None


def test_precedence_spend_then_slices_then_workers_then_clock() -> None:
    limits = RunLimits(max_slices=1, max_workers=1, max_seconds=1)
    every = [ev(cost=2_000_000), *slices(1), *hires(2)]
    assert check(every, limits, elapsed=5) == "spend $2 is over the run ceiling of $1"
    no_spend = [*slices(1), *hires(2)]
    assert check(no_spend, limits, elapsed=5) == "1 slices started; the run limit is 1"
    assert check(hires(2), limits, elapsed=5) == "2 workers hired; the run limit is 1"
    assert check([], limits, elapsed=5) == "5s of wall clock elapsed; the run limit is 1s"


def test_breach_does_not_mutate_events() -> None:
    events = slices(3)
    limits = RunLimits(max_slices=3)
    assert check(events, limits) == check(events, limits)
    assert len(events) == 3


def test_property_breach_is_none_exactly_when_all_four_conditions_hold() -> None:
    rng = random.Random(20260930)
    kinds = list(EventType)
    for _ in range(1000):
        events = [
            ev(
                rng.choice(kinds),
                round_n=rng.randint(0, 3),
                cost=rng.choice([None, 0, rng.randint(0, 300_000)]),
            )
            for _ in range(rng.randint(0, 25))
        ]
        limits = RunLimits(
            max_slices=rng.randint(1, 8),
            max_workers=rng.randint(1, 8),
            max_seconds=rng.choice([None, rng.randint(1, 100)]),
        )
        ceiling = rng.randint(0, 2_000_000)
        elapsed = float(rng.randint(0, 120))

        spend_ok = sum(e.cost_micros for e in events if e.round >= 1 and e.cost_micros) <= ceiling
        slices_ok = len([e for e in events if e.event == "slice_start"]) < limits.max_slices
        workers_ok = len([e for e in events if e.event == "hired"]) <= limits.max_workers
        clock_ok = limits.max_seconds is None or elapsed < limits.max_seconds

        result = check(events, limits, ceiling, elapsed)
        assert (result is None) == (spend_ok and slices_ok and workers_ok and clock_ok)
