import json
from pathlib import Path

import pytest

from antstreet.errors import Outcome, classify
from antstreet.stream import StreamReader, Usage

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> StreamReader:
    reader = StreamReader()
    for line in (FIXTURES / name).read_text().splitlines():
        reader.feed(line)
    return reader


# Expected values copied from the probe output recorded on 2026-09-30.
@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("stream_safe_mode_ok_2.1.285.jsonl", Usage(9927, 10 + 4186, 33, 13796)),
        ("stream_budget_capped_2.1.285.jsonl", Usage(7914, 18 + 1481, 775, 10585)),
        ("stream_auth_expired_2.1.285.jsonl", Usage(0, 0, 0, 0)),
    ],
)
def test_usage_matches_the_recorded_result(fixture, expected):
    assert read(fixture).usage() == expected


def test_capped_run_counts_the_response_that_crossed_the_cap():
    # Top-level `usage` omits the crossing response on a budget cap; `modelUsage` includes it.
    reader = read("stream_budget_capped_2.1.285.jsonl")
    assert reader.result["usage"]["output_tokens"] == 370
    assert reader.usage().tokens_out == 775


def test_resumed_session_reports_cumulative_totals():
    capped, resumed = (
        read("stream_budget_capped_2.1.285.jsonl"),
        read("stream_resume_after_cap_2.1.285.jsonl"),
    )
    assert resumed.usage().cost_micros == 29216
    assert resumed.usage().cost_micros > capped.usage().cost_micros


def test_a_resumed_sessions_tokens_are_cumulative_too_and_top_level_usage_is_the_slice():
    capped, resumed = (
        read("stream_budget_capped_2.1.285.jsonl").usage(),
        read("stream_resume_after_cap_2.1.285.jsonl"),
    )
    own = resumed.result["usage"]  # recorded: only the resumed slice's own response(s)
    after = resumed.usage()
    assert after.cumulative and capped.cumulative
    assert (
        after.tokens_in - capped.tokens_in
        == own["input_tokens"] + own["cache_creation_input_tokens"]
    )
    assert after.tokens_out - capped.tokens_out == own["output_tokens"]
    assert after.tokens_cached - capped.tokens_cached == own["cache_read_input_tokens"]


def test_usage_without_totals_is_not_cumulative():
    assert not read("stream_auth_expired_2.1.285.jsonl").usage().cumulative


def test_outcomes_flow_through_to_the_classifier():
    assert classify(read("stream_auth_expired_2.1.285.jsonl").signals()) is Outcome.LOGIN
    assert classify(read("stream_budget_capped_2.1.285.jsonl").signals()) is Outcome.CAPPED
    assert classify(read("stream_safe_mode_ok_2.1.285.jsonl").signals()) is Outcome.COMPLETED


def test_a_login_whose_refresh_failed_is_login_not_an_api_error():
    # CLI 2.1.292 reports it only on a synthetic assistant message: no retry, no HTTP status.
    reader = read("stream_auth_refresh_failed_2.1.292.jsonl")
    assert reader.message_errors == ["authentication_failed"]
    assert reader.result["terminal_reason"] == "api_error"
    assert classify(reader.signals()) is Outcome.LOGIN


def test_retry_errors_and_hook_events_are_collected():
    reader = read("stream_auth_expired_2.1.285.jsonl")
    assert reader.retry_errors == ["authentication_failed", "authentication_failed"]
    assert reader.hook_events == 2


def test_structured_status_and_denials():
    reader = read("stream_structured_status_blocked_2.1.285.jsonl")
    assert reader.status is not None
    assert reader.status["status"] == "blocked"
    assert [(d["tool"], d["reason"]) for d in reader.denials] == [("Write", "mode")]


def test_permission_denials_fixture_records_both_refusals():
    reader = read("stream_permission_denials_2.1.285.jsonl")
    assert [d["tool"] for d in reader.denials] == ["Write", "Read"]
    assert len(reader.result["permission_denials"]) == 2


def test_init_and_session_id():
    reader = read("stream_safe_mode_ok_2.1.285.jsonl")
    assert reader.init is not None
    assert reader.init["claude_code_version"] == "2.1.285"
    assert reader.session_id == "00000000-0000-0000-0000-000000000000"


def test_unknown_events_and_garbage_are_counted_not_fatal():
    reader = StreamReader()
    for line in [
        '{"type": "brand_new_event", "x": 1}',
        "not json at all",
        "[1, 2, 3]",
        "",
        '{"type": "system", "subtype": "shiny_new_subtype"}',
    ]:
        reader.feed(line)
    assert reader.malformed_lines == 2
    assert reader.event_counts == {"brand_new_event": 1, "system/shiny_new_subtype": 1}
    assert reader.result is None


def test_no_result_means_unknown_cost_and_a_crash():
    reader = StreamReader()
    reader.feed(json.dumps({"type": "system", "subtype": "init", "session_id": "s"}))
    assert reader.usage() == Usage(None, 0, 0, 0)
    assert classify(reader.signals()) is Outcome.CRASHED


def test_zeroed_totals_after_a_crash_are_unknown_not_free():
    reader = StreamReader()
    reader.feed(
        json.dumps(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "total_cost_usd": 0,
                "modelUsage": {},
            }
        )
    )
    assert reader.usage().cost_micros is None


@pytest.mark.parametrize("bad", [None, "0.01", True, -1])
def test_missing_or_invalid_cost_is_unknown(bad):
    reader = StreamReader()
    reader.feed(json.dumps({"type": "result", "subtype": "success", "total_cost_usd": bad}))
    assert reader.usage().cost_micros is None


def result_reader(**fields) -> StreamReader:
    reader = StreamReader()
    reader.feed(json.dumps({"type": "result", "subtype": "success", **fields}))
    assert reader.result is not None
    return reader


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 1e308, [], {}, "x"])
def test_non_finite_or_unscalable_cost_is_unknown_never_a_crash(bad):
    assert result_reader(total_cost_usd=bad).usage().cost_micros is None


def test_an_int_cost_too_big_for_a_float_does_not_crash():
    assert result_reader(total_cost_usd=10**400).usage().cost_micros == 10**406


@pytest.mark.parametrize("bad", [5, "x", None, [], [{"inputTokens": 1}]])
def test_model_usage_of_the_wrong_shape_is_zero_tokens(bad):
    assert result_reader(total_cost_usd=0.5, modelUsage=bad).usage() == Usage(500_000, 0, 0, 0)


def test_model_usage_entries_that_are_not_objects_are_skipped_not_fatal():
    good = {"inputTokens": 3, "cacheCreationInputTokens": 4, "outputTokens": 5}
    usage = result_reader(total_cost_usd=1, modelUsage={"a": 7, "b": None, "c": good}).usage()
    assert usage == Usage(1_000_000, 7, 5, 0)


@pytest.mark.parametrize("bad", [None, "12", -1, float("nan"), float("inf"), 1.5, True, [], {}])
def test_bad_token_counts_are_zero_and_good_ones_survive(bad):
    model = {
        "inputTokens": bad,
        "cacheCreationInputTokens": 2,
        "outputTokens": bad,
        "cacheReadInputTokens": bad,
    }
    assert result_reader(total_cost_usd=0, modelUsage={"m": model}).usage() == Usage(0, 2, 0, 0)


@pytest.mark.parametrize("line", ["1" * 4301, "[" * 100_000, '{"a":' * 100_000])
def test_feed_never_raises_and_counts_the_line_as_malformed(line):
    reader = StreamReader()
    reader.feed(line)
    assert reader.malformed_lines == 1
    assert reader.usage() == Usage(None, 0, 0, 0)


def test_timeout_flag_reaches_the_signals():
    assert read("stream_safe_mode_ok_2.1.285.jsonl").signals(timed_out=True).timed_out
