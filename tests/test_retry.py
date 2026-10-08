import pytest

from antstreet.errors import INFRASTRUCTURE, Outcome
from antstreet.retry import GiveUp, Pause, Wait, infra_action, plan_pressure

SAMPLE = {
    "status": "allowed",
    "resetsAt": 1790763600,
    "rateLimitType": "five_hour",
    "overageStatus": "rejected",
    "isUsingOverage": False,
    "unifiedWindows": {
        "five_hour": {"utilization": 0.08, "resetsAt": 1790763600},
        "seven_day": {"utilization": 0.11, "resetsAt": 1791165600},
    },
}


def windows(**named: tuple[float, float]) -> dict:
    return {"unifiedWindows": {k: {"utilization": u, "resetsAt": r} for k, (u, r) in named.items()}}


@pytest.mark.parametrize("outcome", [Outcome.RATE_LIMITED, Outcome.API_ERROR])
@pytest.mark.parametrize(
    ("jitter", "expected"),
    [
        (0.0, [2.5, 5.0, 10.0, 20.0, None, None]),
        (0.5, [3.75, 7.5, 15.0, 30.0, None, None]),
    ],
)
def test_backoff_doubles_with_equal_jitter(outcome, jitter, expected):
    for attempt, seconds in enumerate(expected, start=1):
        action = infra_action(outcome, attempt, None, max_attempts=4, jitter=lambda: jitter)
        if seconds is None:
            assert isinstance(action, GiveUp)
        else:
            assert action == Wait(seconds, f"{outcome.value}, attempt {attempt} of 4")


def test_backoff_is_capped():
    def seconds(attempt: int, jitter: float) -> float:
        action = infra_action(
            Outcome.API_ERROR, attempt, None, max_attempts=10, jitter=lambda: jitter
        )
        assert isinstance(action, Wait)
        return action.seconds

    assert [seconds(a, 0.0) for a in (5, 6, 7, 10)] == [40.0, 60.0, 60.0, 60.0]
    assert [seconds(a, 0.5) for a in (5, 6, 7, 10)] == [60.0, 90.0, 90.0, 90.0]
    assert seconds(10, 0.999) < 120.0


def test_default_jitter_stays_within_bounds():
    for _ in range(50):
        action = infra_action(Outcome.RATE_LIMITED, 3, None)
        assert isinstance(action, Wait)
        assert 10.0 <= action.seconds < 20.0


def test_wait_reason_names_outcome_and_attempt():
    action = infra_action(Outcome.RATE_LIMITED, 2, None, jitter=lambda: 0.0)
    assert isinstance(action, Wait)
    assert "rate_limited" in action.reason
    assert "2" in action.reason


@pytest.mark.parametrize(
    ("outcome", "fix_word"),
    [(Outcome.RATE_LIMITED, "later"), (Outcome.API_ERROR, "status")],
)
def test_gives_up_after_max_attempts(outcome, fix_word):
    action = infra_action(outcome, 3, None, max_attempts=2)
    assert isinstance(action, GiveUp)
    assert fix_word in action.fix
    assert isinstance(infra_action(outcome, 2, None, max_attempts=2), Wait)


@pytest.mark.parametrize("attempt", [1, 2, 4, 5, 100])
def test_login_never_waits(attempt):
    action = infra_action(Outcome.LOGIN, attempt, None)
    assert isinstance(action, GiveUp)
    assert "claude auth login" in action.fix


def test_usage_limit_pauses_until_top_level_reset():
    action = infra_action(Outcome.USAGE_LIMIT, 1, SAMPLE)
    assert action == Pause(1790763600, "plan usage limit reached")


def test_usage_limit_top_level_beats_saturated_window():
    rate_limit = {"resetsAt": 500, **windows(five_hour=(1.0, 900))}
    assert infra_action(Outcome.USAGE_LIMIT, 1, rate_limit) == Pause(
        500, "plan usage limit reached"
    )


def test_usage_limit_uses_earliest_saturated_window():
    rate_limit = windows(five_hour=(1.0, 900), seven_day=(1.2, 700), other=(0.5, 100))
    action = infra_action(Outcome.USAGE_LIMIT, 1, rate_limit)
    assert isinstance(action, Pause)
    assert action.until_epoch == 700


@pytest.mark.parametrize(
    "rate_limit",
    [
        None,
        {},
        {"resetsAt": 0},
        {"resetsAt": -5},
        {"resetsAt": "1790763600"},
        {"resetsAt": True},
        windows(five_hour=(0.5, 900)),
        windows(five_hour=(1.0, 0)),
        {"unifiedWindows": "nope"},
    ],
)
def test_usage_limit_with_nothing_usable_has_unknown_reset(rate_limit):
    action = infra_action(Outcome.USAGE_LIMIT, 1, rate_limit)
    assert isinstance(action, Pause)
    assert action.until_epoch is None


def test_usage_limit_is_not_capped_by_attempts():
    assert isinstance(infra_action(Outcome.USAGE_LIMIT, 99, None, max_attempts=1), Pause)


@pytest.mark.parametrize("outcome", sorted(set(Outcome) - INFRASTRUCTURE))
def test_non_infrastructure_outcome_raises(outcome):
    with pytest.raises(ValueError, match="infrastructure"):
        infra_action(outcome, 1, None)


@pytest.mark.parametrize("attempt", [0, -1])
def test_attempt_below_one_raises(attempt):
    with pytest.raises(ValueError, match="attempt"):
        infra_action(Outcome.RATE_LIMITED, attempt, None)


def test_pressure_below_at_and_above_threshold():
    assert plan_pressure(windows(five_hour=(0.89, 900))) is None
    at = plan_pressure(windows(five_hour=(0.9, 900)))
    assert at == Pause(900, "five_hour window at 90% of the plan limit")
    above = plan_pressure(windows(five_hour=(0.97, 900)))
    assert isinstance(above, Pause)
    assert "97%" in above.reason


def test_pressure_two_windows_over_threshold_picks_later_reset():
    action = plan_pressure(windows(five_hour=(0.95, 900), seven_day=(0.91, 5000)))
    assert isinstance(action, Pause)
    assert action.until_epoch == 5000
    assert "seven_day" in action.reason
    assert "91%" in action.reason


def test_pressure_ignores_windows_under_threshold_when_picking():
    action = plan_pressure(windows(five_hour=(0.95, 900), seven_day=(0.2, 5000)))
    assert isinstance(action, Pause)
    assert action.until_epoch == 900


def test_pressure_custom_threshold():
    assert plan_pressure(windows(five_hour=(0.5, 900)), threshold=0.5) is not None
    assert plan_pressure(windows(five_hour=(0.5, 900)), threshold=0.51) is None


@pytest.mark.parametrize(
    "rate_limit",
    [
        None,
        {},
        "rate limited",
        [],
        42,
        {"unifiedWindows": None},
        {"unifiedWindows": "five_hour"},
        {"unifiedWindows": []},
        {"unifiedWindows": {"five_hour": None}},
        {"unifiedWindows": {"five_hour": "0.99"}},
        {"unifiedWindows": {"five_hour": {}}},
        {"unifiedWindows": {"five_hour": {"resetsAt": 900}}},
        {"unifiedWindows": {"five_hour": {"utilization": 0.99}}},
        {"unifiedWindows": {"five_hour": {"utilization": "0.99", "resetsAt": 900}}},
        {"unifiedWindows": {"five_hour": {"utilization": 0.99, "resetsAt": "900"}}},
        {"unifiedWindows": {"five_hour": {"utilization": 0.99, "resetsAt": None}}},
        {"unifiedWindows": {"five_hour": {"utilization": True, "resetsAt": 900}}},
        {"unifiedWindows": {"five_hour": {"utilization": float("nan"), "resetsAt": 900}}},
        {"unifiedWindows": {"five_hour": {"utilization": 0.99, "resetsAt": float("inf")}}},
    ],
)
def test_pressure_malformed_input_is_absent(rate_limit):
    assert plan_pressure(rate_limit) is None


def test_pressure_one_bad_window_does_not_hide_a_good_one():
    rate_limit = {
        "unifiedWindows": {
            "broken": {"utilization": "high", "resetsAt": 1},
            "five_hour": {"utilization": 0.95, "resetsAt": 900},
        }
    }
    action = plan_pressure(rate_limit)
    assert isinstance(action, Pause)
    assert action.until_epoch == 900


def test_recorded_sample_has_no_pressure_by_default():
    assert plan_pressure(SAMPLE) is None


def test_recorded_sample_at_low_threshold_names_the_later_window():
    action = plan_pressure(SAMPLE, threshold=0.05)
    assert isinstance(action, Pause)
    assert action.until_epoch == 1791165600
    assert "seven_day" in action.reason
    assert "11%" in action.reason


def test_a_lost_session_is_retried_at_once_with_a_new_one_and_only_once():
    first = infra_action(Outcome.SESSION_LOST, 1, None)
    assert first == Wait(0.0, "the session to resume no longer exists; starting a new one")
    second = infra_action(Outcome.SESSION_LOST, 2, None)
    assert isinstance(second, GiveUp) and "session store" in second.fix
