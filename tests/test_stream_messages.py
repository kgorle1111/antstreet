"""Input tokens recovered from per-message usage when the stream has no final totals."""

import json
from pathlib import Path

import pytest

from boss.stream import StreamReader, Usage

FIXTURES = Path(__file__).parent / "fixtures"


def lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


def message(mid, usage, block="text"):
    return json.dumps({"type": "assistant", "message": {"id": mid, "usage": usage, "x": block}})


def feed(*items: str) -> StreamReader:
    reader = StreamReader()
    for item in items:
        reader.feed(item)
    return reader


def killed(name: str) -> StreamReader:
    """The recorded stream cut off before its result, as a killed slice would be."""
    return feed(*(ln for ln in lines(name) if '"type": "result"' not in ln))


def input_side(totals: dict) -> tuple[int, int]:
    """(input + cache creation, cache read) from a modelUsage-style or top-level usage dict."""
    return (
        totals.get("inputTokens", totals.get("input_tokens", 0))
        + totals.get("cacheCreationInputTokens", totals.get("cache_creation_input_tokens", 0)),
        totals.get("cacheReadInputTokens", totals.get("cache_read_input_tokens", 0)),
    )


# The per-message sums against what the final result of the same stream reports. A resumed
# session's `modelUsage` is cumulative over earlier slices, so its slice-only figure is `usage`.
@pytest.mark.parametrize(
    ("fixture", "figures"),
    [
        ("stream_safe_mode_ok_2.1.285.jsonl", "modelUsage"),
        ("stream_budget_capped_2.1.285.jsonl", "modelUsage"),  # `usage` omits the crossing response
        ("stream_structured_status_blocked_2.1.285.jsonl", "modelUsage"),
        ("stream_resume_after_cap_2.1.285.jsonl", "usage"),
    ],
)
def test_summed_messages_equal_the_recorded_final_totals(fixture, figures):
    result = next(json.loads(ln) for ln in lines(fixture) if '"type": "result"' in ln)
    raw = result[figures]
    totals = next(iter(raw.values())) if figures == "modelUsage" else raw
    tokens_in, tokens_cached = input_side(totals)
    assert tokens_in > 0  # the proof is not about zeros
    assert killed(fixture).usage() == Usage(None, tokens_in, 0, tokens_cached)


def test_one_message_is_counted_once_however_many_blocks_it_streams_in():
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 7}
    one = feed(message("m1", usage, "thinking"), message("m1", usage, "text")).usage()
    assert one == Usage(None, 110, 0, 7)
    two = feed(message("m1", usage), message("m2", usage)).usage()
    assert two == Usage(None, 220, 0, 14)


def test_output_tokens_stay_zero_because_the_per_message_figure_is_a_placeholder():
    usage = {"input_tokens": 1, "output_tokens": 3}
    assert feed(message("m1", usage)).usage().tokens_out == 0


@pytest.mark.parametrize(
    "event",
    [
        {"type": "assistant"},
        {"type": "assistant", "message": "text"},
        {"type": "assistant", "message": {"usage": {"input_tokens": 5}}},  # no id
        {"type": "assistant", "message": {"id": 7, "usage": {"input_tokens": 5}}},
        {"type": "assistant", "message": {"id": "m", "usage": [5]}},
        {"type": "assistant", "message": {"id": "m", "usage": {"input_tokens": True}}},
        {"type": "assistant", "message": {"id": "m", "usage": {"input_tokens": -4}}},
    ],
)
def test_malformed_message_usage_is_ignored_not_fatal(event):
    assert feed(json.dumps(event)).usage() == Usage(None, 0, 0, 0)


def test_a_result_with_totals_is_never_added_to_the_message_sums():
    result = {"type": "result", "total_cost_usd": 0.5, "modelUsage": {"m": {"inputTokens": 2}}}
    reader = feed(message("m1", {"input_tokens": 99}), json.dumps(result))
    assert reader.usage() == Usage(500_000, 2, 0, 0)


def test_a_crashed_result_with_zeroed_totals_falls_back_to_messages_and_unknown_cost():
    result = {"type": "result", "subtype": "error_during_execution", "total_cost_usd": 0}
    reader = feed(
        message("m1", {"input_tokens": 3, "cache_read_input_tokens": 4}), json.dumps(result)
    )
    assert reader.usage() == Usage(None, 3, 0, 4)


def test_a_result_without_model_usage_keeps_its_cost_and_gains_the_message_tokens():
    result = {"type": "result", "subtype": "success", "total_cost_usd": 0.25}
    reader = feed(message("m1", {"input_tokens": 3}), json.dumps(result))
    assert reader.usage() == Usage(250_000, 3, 0, 0)


@pytest.mark.parametrize(
    "fixture",
    [
        "stream_budget_capped_2.1.285.jsonl",
        "stream_structured_status_blocked_2.1.285.jsonl",
        "stream_resume_after_cap_2.1.285.jsonl",
    ],
)
def test_per_message_output_tokens_are_a_small_fraction_of_the_billed_output(fixture):
    # Why there is no cost watch (D37): output, a large share of the cost, is not in the stream
    # until the result, and nothing but the result carries a cost.
    events = [json.loads(ln) for ln in lines(fixture)]
    per_message = {
        e["message"]["id"]: e["message"]["usage"]["output_tokens"]
        for e in events
        if e["type"] == "assistant"
    }
    result = next(e for e in events if e["type"] == "result")
    billed = sum(m["outputTokens"] for m in result["modelUsage"].values())
    assert sum(per_message.values()) * 20 < billed
    assert not any("cost" in key.lower() for e in events[:-1] for key in e)
