"""Incremental reader for the CLI's `stream-json` output.

Tolerant by design: unknown event types and non-JSON lines are counted, never fatal, because the
CLI adds event types between versions. Money and outcome come only from the final `result` event.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from boss.errors import RunSignals

MICROS_PER_USD = 1_000_000
# json.loads joins an escaped surrogate pair into one character, so any surrogate left is a lone
# one: valid JSON, but text that no UTF-8 file, report or check can hold.
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


@dataclass(frozen=True, slots=True)
class Usage:
    """Session totals from `modelUsage`, which, unlike top-level `usage`, includes subagents and
    the response that crossed a budget cap. After a resume they are cumulative for the session.

    `cumulative` says the tokens are those session totals. A slice with no totals (killed, or the
    CLI zeroed them) carries the input-side sums of its own messages instead, and is False.
    """

    cost_micros: int | None  # None = unknown
    tokens_in: int  # input + cache-creation tokens, both billed as input
    tokens_out: int
    tokens_cached: int  # cache reads
    cumulative: bool = field(default=False, compare=False)  # metadata: equal figures are equal


class StreamReader:
    def __init__(self) -> None:
        self.init: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.retry_errors: list[str] = []
        self.message_errors: list[str] = []
        self.rate_limit: dict[str, Any] | None = None
        self.denials: list[dict[str, Any]] = []
        self.hook_events = 0
        self.malformed_lines = 0
        self.event_counts: Counter[str] = Counter()
        # Per message id: the CLI emits one `assistant` event per content block, each repeating
        # the message's usage, so counting events would count a message once per block.
        self._messages: dict[str, tuple[int, int, int]] = {}  # id -> in, cache write, cache read

    def feed(self, line: str) -> None:
        if not line.strip():
            return
        try:
            event = _valid_text(json.loads(line))
        except (ValueError, RecursionError):  # not only JSONDecodeError: int digit limit, nesting
            self.malformed_lines += 1
            return
        if not isinstance(event, dict):
            self.malformed_lines += 1
            return
        kind, subtype = str(event.get("type", "")), str(event.get("subtype", ""))
        self.event_counts[f"{kind}/{subtype}" if subtype else kind] += 1
        if kind == "system":
            self._system(subtype, event)
        elif kind == "rate_limit_event" and isinstance(event.get("rate_limit_info"), dict):
            self.rate_limit = event["rate_limit_info"]
        elif kind == "assistant":
            self._message(event.get("message"))
            if event.get("is_api_error_message") is True:
                self.message_errors.append(str(event.get("error", "unknown")))
        elif kind == "result":
            self.result = event

    def _system(self, subtype: str, event: dict[str, Any]) -> None:
        if subtype == "init":
            self.init = event
        elif subtype == "api_retry":
            self.retry_errors.append(str(event.get("error", "unknown")))
        elif subtype == "permission_denied":
            self.denials.append(
                {
                    "tool": event.get("tool_name"),
                    "reason": event.get("decision_reason_type"),
                    "message": event.get("message"),
                }
            )
        elif subtype.startswith("hook_"):
            self.hook_events += 1

    def _message(self, message: Any) -> None:
        usage = message.get("usage") if isinstance(message, dict) else None
        mid = message.get("id") if isinstance(message, dict) else None
        if not isinstance(usage, dict) or not isinstance(mid, str):
            return
        self._messages[mid] = (
            _count(usage, "input_tokens"),
            _count(usage, "cache_creation_input_tokens"),
            _count(usage, "cache_read_input_tokens"),
        )

    @property
    def session_id(self) -> str | None:
        for event in (self.result, self.init):
            if event and event.get("session_id"):
                return str(event["session_id"])
        return None

    @property
    def status(self) -> dict[str, Any] | None:
        """The worker's structured status object, if it returned one."""
        output = (self.result or {}).get("structured_output")
        return output if isinstance(output, dict) else None

    def signals(self, *, timed_out: bool = False, stderr_tail: str = "") -> RunSignals:
        return RunSignals(
            result=self.result,
            retry_errors=tuple(self.retry_errors),
            message_errors=tuple(self.message_errors),
            rate_limit_status=(self.rate_limit or {}).get("status"),
            timed_out=timed_out,
            stderr_tail=stderr_tail,
        )

    def usage(self) -> Usage:
        result = self.result
        raw = (result or {}).get("modelUsage")
        models = [m for m in raw.values() if isinstance(m, dict)] if isinstance(raw, dict) else []
        if result is None or not models:
            return self._message_usage(None if result is None else _cost_micros(result, False))
        tokens_in = sum(
            _count(m, "inputTokens") + _count(m, "cacheCreationInputTokens") for m in models
        )
        tokens_out = sum(_count(m, "outputTokens") for m in models)
        tokens_cached = sum(_count(m, "cacheReadInputTokens") for m in models)
        return Usage(
            _cost_micros(result, bool(models)),
            tokens_in,
            tokens_out,
            tokens_cached,
            cumulative=True,
        )

    def _message_usage(self, cost_micros: int | None) -> Usage:
        """Input-side tokens summed from the messages seen, for a slice with no totals: it was
        killed, or the CLI zeroed them. Output stays 0: each message's `output_tokens` is its
        count at the start of the response (4 against 775 billed in the capped fixture), so a sum
        of them would look measured and be wrong. The cost stays unknown for the same reason."""
        sums = [sum(m[i] for m in self._messages.values()) for i in range(3)]
        return Usage(cost_micros, sums[0] + sums[1], 0, sums[2])


def _count(model: dict[str, Any], key: str) -> int:
    value = model.get(key)
    # bool is an int subclass; a malformed count is 0 (an undercount), never an exception.
    return value if type(value) is int and value >= 0 else 0


def _cost_micros(result: dict[str, Any], has_model_usage: bool) -> int | None:
    cost = result.get("total_cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, int | float) or cost < 0:
        return None
    # Docs: after a session crash every cost field may be zeroed, so zero there means unknown.
    if result.get("subtype") == "error_during_execution" and not has_model_usage:
        return None
    try:
        return round(cost * MICROS_PER_USD)
    except (ValueError, OverflowError):  # NaN, or a figure too large to scale (1e308)
        return None


def _valid_text(value: Any) -> Any:
    """Every string in a parsed event, with each lone surrogate replaced by U+FFFD: the same
    replacement the runner applies to undecodable output, applied once here for every reader."""
    if isinstance(value, str):
        return _LONE_SURROGATE.sub("\ufffd", value)
    if isinstance(value, list):
        return [_valid_text(v) for v in value]
    if isinstance(value, dict):
        return {_valid_text(k): _valid_text(v) for k, v in value.items()}
    return value
