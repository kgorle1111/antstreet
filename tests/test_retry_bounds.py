import pytest

from antstreet.errors import Outcome
from antstreet.retry import Pause, Wait, infra_action, plan_pressure


def windows(**named: tuple[float, float]) -> dict:
    return {"unifiedWindows": {k: {"utilization": u, "resetsAt": r} for k, (u, r) in named.items()}}


@pytest.mark.parametrize("attempt", [50, 1024, 1500, 10**6, 10**30])
@pytest.mark.parametrize("outcome", [Outcome.RATE_LIMITED, Outcome.API_ERROR])
def test_a_huge_attempt_number_waits_the_cap_and_does_not_overflow(outcome, attempt):
    high = infra_action(outcome, attempt, None, max_attempts=10**31, jitter=lambda: 1.0)
    low = infra_action(outcome, attempt, None, max_attempts=10**31, jitter=lambda: 0.0)
    assert isinstance(high, Wait)
    assert isinstance(low, Wait)
    assert (low.seconds, high.seconds) == (60.0, 120.0)


def test_a_huge_attempt_with_a_huge_base_still_waits_the_cap():
    action = infra_action(
        Outcome.RATE_LIMITED, 5000, None, max_attempts=10**6, base_s=1e300, jitter=lambda: 1.0
    )
    assert isinstance(action, Wait)
    assert action.seconds == 120.0


@pytest.mark.parametrize("utilization", [1.5, 5, 90, 95, 100, -0.5, -1, 1.0000001])
def test_a_utilization_outside_zero_to_one_is_unknown_not_pressure(utilization):
    assert plan_pressure(windows(five_hour=(utilization, 900))) is None
    assert plan_pressure(windows(five_hour=(utilization, 900)), threshold=0.0) is None


def test_one_out_of_range_window_does_not_hide_a_good_one():
    action = plan_pressure(windows(five_hour=(95, 9000), seven_day=(0.95, 900)))
    assert isinstance(action, Pause)
    assert action.until_epoch == 900


def test_a_utilization_of_exactly_one_is_full_pressure():
    action = plan_pressure(windows(five_hour=(1.0, 900)))
    assert action == Pause(900, "five_hour window at 100% of the plan limit")


def test_zero_utilization_is_pressure_only_with_a_zero_threshold():
    assert plan_pressure(windows(five_hour=(0.0, 900))) is None
    assert isinstance(plan_pressure(windows(five_hour=(0.0, 900)), threshold=0.0), Pause)
