"""Stream reader edge cases: partial sessions, odd event shapes and malformed usage blocks."""

import json

import pytest

from boss.stream import StreamReader, Usage


def reader(*events: object) -> StreamReader:
    r = StreamReader()
    for event in events:
        r.feed(event if isinstance(event, str) else json.dumps(event))
    return r


def result(**fields) -> dict:
    return {"type": "result", "subtype": "success", "modelUsage": {"m": {}}} | fields


def test_session_id_is_none_without_any_session_event():
    assert reader({"type": "assistant"}).session_id is None


def test_session_id_is_none_when_the_ids_are_empty():
    r = reader({"type": "system", "subtype": "init", "session_id": ""}, result(session_id=None))
    assert r.session_id is None


def test_result_session_id_wins_over_the_init_one():
    r = reader(
        {"type": "system", "subtype": "init", "session_id": "from-init"},
        result(session_id="from-result"),
    )
    assert r.session_id == "from-result"


def test_init_session_id_is_used_when_the_run_died_before_a_result():
    assert reader({"type": "system", "subtype": "init", "session_id": "s1"}).session_id == "s1"


def test_blank_and_whitespace_lines_are_ignored_entirely():
    r = reader("", "   ", "\n")
    assert r.malformed_lines == 0
    assert not r.event_counts


@pytest.mark.parametrize("line", ["[1, 2]", "7", '"text"', "null", "{broken"])
def test_non_object_json_and_broken_json_are_counted_as_malformed(line):
    r = reader(line)
    assert r.malformed_lines == 1
    assert not r.event_counts


def test_event_counts_key_on_type_and_subtype():
    r = reader(
        {"type": "system", "subtype": "hook_started"},
        {"type": "system", "subtype": "hook_response"},
        {"type": "assistant"},
        {"type": "assistant"},
    )
    assert dict(r.event_counts) == {
        "system/hook_started": 1,
        "system/hook_response": 1,
        "assistant": 2,
    }
    assert r.hook_events == 2


def test_event_without_a_type_is_counted_under_the_empty_name():
    assert dict(reader({"hello": 1}).event_counts) == {"": 1}


def test_api_retry_without_an_error_field_is_recorded_as_unknown():
    r = reader({"type": "system", "subtype": "api_retry"})
    assert r.retry_errors == ["unknown"]


def test_permission_denied_without_details_records_none_values():
    r = reader({"type": "system", "subtype": "permission_denied"})
    assert r.denials == [{"tool": None, "reason": None}]


def test_rate_limit_event_without_an_info_object_is_ignored():
    r = reader({"type": "rate_limit_event", "rate_limit_info": "nope"})
    assert r.rate_limit is None
    assert r.signals().rate_limit_status is None


def test_last_rate_limit_event_wins():
    r = reader(
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}},
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}},
    )
    assert r.signals().rate_limit_status == "rejected"


def test_last_result_event_wins():
    r = reader(result(total_cost_usd=1), result(total_cost_usd=2))
    assert r.usage().cost_micros == 2_000_000


def test_status_is_none_unless_structured_output_is_an_object():
    assert reader(result(structured_output=[1])).status is None
    assert reader(result(structured_output="done")).status is None
    assert reader({"type": "assistant"}).status is None
    assert reader(result(structured_output={"ok": True})).status == {"ok": True}


def test_signals_carry_the_collected_evidence():
    r = reader(
        {"type": "system", "subtype": "api_retry", "error": "rate_limit"},
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}},
        result(),
    )
    signals = r.signals(timed_out=True)
    assert signals.retry_errors == ("rate_limit",)
    assert signals.rate_limit_status == "rejected"
    assert signals.timed_out is True
    assert signals.result is r.result


def test_tokens_sum_over_every_model_and_cache_creation_counts_as_input():
    r = reader(
        result(
            total_cost_usd=0.5,
            modelUsage={
                "a": {
                    "inputTokens": 10,
                    "cacheCreationInputTokens": 5,
                    "outputTokens": 3,
                    "cacheReadInputTokens": 100,
                },
                "b": {"inputTokens": 1, "outputTokens": 2},
            },
        )
    )
    assert r.usage() == Usage(500_000, tokens_in=16, tokens_out=5, tokens_cached=100)


def test_cost_is_rounded_to_whole_micros():
    assert reader(result(total_cost_usd=0.0000004)).usage().cost_micros == 0
    assert reader(result(total_cost_usd=0.0000006)).usage().cost_micros == 1


def test_a_zero_cost_with_a_model_breakdown_is_really_zero():
    assert reader(result(total_cost_usd=0)).usage().cost_micros == 0


def test_a_null_model_usage_with_a_positive_cost_still_reports_the_cost():
    assert reader(result(total_cost_usd=1, modelUsage=None)).usage() == Usage(1_000_000, 0, 0, 0)


def test_a_nan_cost_is_unknown_not_a_crash():
    # json.loads accepts the bare token NaN, so a hostile or buggy CLI can send it.
    r = reader('{"type": "result", "total_cost_usd": NaN, "modelUsage": {"m": {}}}')
    assert r.usage().cost_micros is None


def test_an_infinite_cost_is_unknown_not_a_crash():
    r = reader('{"type": "result", "total_cost_usd": Infinity, "modelUsage": {"m": {}}}')
    assert r.usage().cost_micros is None


@pytest.mark.parametrize(
    "model_usage",
    [[1], {"m": 3}, {"m": {"inputTokens": "many"}}, {"m": {"inputTokens": None}}],
    ids=["list", "non-dict-entry", "string-count", "null-count"],
)
def test_malformed_model_usage_degrades_instead_of_raising(model_usage):
    usage = reader(result(total_cost_usd=1, modelUsage=model_usage)).usage()
    assert usage.cost_micros in (None, 1_000_000)
