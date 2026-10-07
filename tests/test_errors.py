import json
from pathlib import Path

import pytest

from boss.errors import INFRASTRUCTURE, Outcome, RunSignals, classify

FIXTURES = Path(__file__).parent / "fixtures"


def signals_from_fixture(name: str, **result_overrides) -> RunSignals:
    events = [json.loads(line) for line in (FIXTURES / name).read_text().splitlines()]
    result = next(e for e in reversed(events) if e.get("type") == "result")
    retries = tuple(e["error"] for e in events if e.get("subtype") == "api_retry")
    limits = [e["rate_limit_info"]["status"] for e in events if e.get("type") == "rate_limit_event"]
    return RunSignals(
        result=result | result_overrides,
        retry_errors=retries,
        rate_limit_status=limits[-1] if limits else None,
    )


OK = "stream_safe_mode_ok_2.1.285.jsonl"


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("stream_auth_expired_2.1.285.jsonl", Outcome.LOGIN),
        ("stream_budget_capped_2.1.285.jsonl", Outcome.CAPPED),
        (OK, Outcome.COMPLETED),
        ("stream_resume_after_cap_2.1.285.jsonl", Outcome.COMPLETED),
        ("stream_permission_denials_2.1.285.jsonl", Outcome.COMPLETED),
        ("stream_structured_status_blocked_2.1.285.jsonl", Outcome.COMPLETED),
    ],
)
def test_recorded_streams(fixture, expected):
    assert classify(signals_from_fixture(fixture)) is expected


def test_failed_login_is_not_trusted_as_success_despite_its_subtype():
    signals = signals_from_fixture("stream_auth_expired_2.1.285.jsonl")
    assert signals.result["subtype"] == "success"
    assert classify(signals) is Outcome.LOGIN


def test_only_an_auth_error_on_an_api_error_message_makes_an_api_error_a_login():
    failed = {"type": "result", "subtype": "success", "is_error": True}
    failed["terminal_reason"] = "api_error"
    assert classify(RunSignals(result=failed)) is Outcome.API_ERROR
    login = RunSignals(result=failed, message_errors=("authentication_failed",))
    assert classify(login) is Outcome.LOGIN
    other = RunSignals(result=failed, message_errors=("overloaded_error",))
    assert classify(other) is Outcome.API_ERROR


# No recording exists for these yet; each is derived from a real result line with changed fields.
@pytest.mark.parametrize(
    ("overrides", "extra", "expected"),
    [
        ({"subtype": "error_max_turns", "is_error": True}, {}, Outcome.MAX_TURNS),
        ({"subtype": "error_max_budget_usd", "terminal_reason": "completed"}, {}, Outcome.CAPPED),
        ({"subtype": "success", "terminal_reason": "budget_exhausted"}, {}, Outcome.CAPPED),
        ({"is_error": True, "api_error_status": 401}, {}, Outcome.LOGIN),
        ({"subtype": "model_refusal", "is_error": False}, {}, Outcome.REFUSAL),
        ({"stop_reason": "refusal"}, {}, Outcome.REFUSAL),
        # 403 is a revoked or forbidden key: a login fix, never an ordinary retry
        ({"is_error": True, "api_error_status": 403}, {}, Outcome.LOGIN),
        ({"is_error": True, "api_error_status": 429}, {}, Outcome.RATE_LIMITED),
        ({"is_error": True, "api_error_status": 529}, {}, Outcome.API_ERROR),
        (
            {"is_error": True, "api_error_status": None, "terminal_reason": "api_error"},
            {},
            Outcome.API_ERROR,
        ),
        ({"is_error": True, "subtype": "error_during_execution"}, {}, Outcome.CRASHED),
        (
            {"is_error": True, "result": "You've hit your limit · resets 4pm"},
            {},
            Outcome.USAGE_LIMIT,
        ),
        ({"is_error": True}, {"rate_limit_status": "rejected"}, Outcome.USAGE_LIMIT),
        ({"is_error": True}, {"retry_errors": ("rate_limit",)}, Outcome.RATE_LIMITED),
    ],
)
def test_derived_outcomes(overrides, extra, expected):
    base = signals_from_fixture(OK, **overrides)
    signals = RunSignals(
        result=base.result,
        retry_errors=extra.get("retry_errors", base.retry_errors),
        rate_limit_status=extra.get("rate_limit_status", base.rate_limit_status),
    )
    assert classify(signals) is expected


def test_no_result_event_is_a_crash():
    assert classify(RunSignals(result=None)) is Outcome.CRASHED


def test_timeout_wins_even_if_a_result_arrived():
    signals = signals_from_fixture(OK)
    assert classify(RunSignals(result=signals.result, timed_out=True)) is Outcome.TIMEOUT


def test_only_provider_side_failures_are_infrastructure():
    assert {
        Outcome.LOGIN,
        Outcome.RATE_LIMITED,
        Outcome.USAGE_LIMIT,
        Outcome.API_ERROR,
        Outcome.SESSION_LOST,
    } == INFRASTRUCTURE
    assert Outcome.CAPPED not in INFRASTRUCTURE
    assert Outcome.TIMEOUT not in INFRASTRUCTURE


# Probe (CLI 2.1.285): resuming a session that does not exist answers "No conversation found".
# The probe was not saved, so the phrase is placed in each stream it might arrive in.
GONE = "No conversation found with session ID: 6f1c1c5e-0d6e-4c53-a4a6-9ad1d5c6a001"


def test_a_session_the_cli_no_longer_has_is_read_from_stderr_when_no_result_arrived():
    assert classify(RunSignals(result=None, stderr_tail=GONE + "\n")) is Outcome.SESSION_LOST
    assert classify(RunSignals(result=None, stderr_tail="Error: something else")) is Outcome.CRASHED
    assert classify(RunSignals(result=None)) is Outcome.CRASHED


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_error": True, "result": GONE},
        {"is_error": True, "subtype": "error_during_execution", "errors": [GONE]},
        {"is_error": True, "errors": GONE},
    ],
)
def test_a_session_the_cli_no_longer_has_is_read_from_the_error_result(overrides):
    assert classify(signals_from_fixture(OK, **overrides)) is Outcome.SESSION_LOST


def test_the_phrase_does_not_turn_a_finished_slice_into_a_lost_session():
    # A worker that quotes it, or a stray stderr line, must not discard a slice that completed.
    ok = signals_from_fixture(OK)
    assert classify(RunSignals(result=ok.result, stderr_tail=GONE)) is Outcome.COMPLETED
    quoted = signals_from_fixture(OK, result=GONE)
    assert classify(quoted) is Outcome.COMPLETED
    assert classify(RunSignals(result=ok.result, timed_out=True, stderr_tail=GONE)) is (
        Outcome.TIMEOUT
    )
