"""Incremental reader for the CLI's `stream-json` output.

Tolerant by design: unknown event types and non-JSON lines are counted, never fatal, because the
CLI adds event types between versions. Money and outcome come only from the final `result` event.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from boss.errors import RunSignals

MICROS_PER_USD = 1_000_000


@dataclass(frozen=True, slots=True)
class Usage:
    """Session totals from `modelUsage`, which, unlike top-level `usage`, includes subagents and
    the response that crossed a budget cap. After a resume they are cumulative for the session.
    """

    cost_micros: int | None  # None = unknown
    tokens_in: int  # input + cache-creation tokens, both billed as input
    tokens_out: int
    tokens_cached: int  # cache reads


class StreamReader:
    def __init__(self) -> None:
        self.init: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.retry_errors: list[str] = []
        self.rate_limit: dict[str, Any] | None = None
        self.denials: list[dict[str, Any]] = []
        self.hook_events = 0
        self.malformed_lines = 0
        self.event_counts: Counter[str] = Counter()

    def feed(self, line: str) -> None:
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
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
        elif kind == "result":
            self.result = event

    def _system(self, subtype: str, event: dict[str, Any]) -> None:
        if subtype == "init":
            self.init = event
        elif subtype == "api_retry":
            self.retry_errors.append(str(event.get("error", "unknown")))
        elif subtype == "permission_denied":
            self.denials.append(
                {"tool": event.get("tool_name"), "reason": event.get("decision_reason_type")}
            )
        elif subtype.startswith("hook_"):
            self.hook_events += 1

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

    def signals(self, *, timed_out: bool = False) -> RunSignals:
        return RunSignals(
            result=self.result,
            retry_errors=tuple(self.retry_errors),
            rate_limit_status=(self.rate_limit or {}).get("status"),
            timed_out=timed_out,
        )

    def usage(self) -> Usage:
        result = self.result
        if result is None:
            # kn: input tokens could be recovered from per-message usage; not needed yet.
            return Usage(None, 0, 0, 0)
        by_model = result.get("modelUsage") or {}
        tokens_in = sum(
            int(m.get("inputTokens", 0)) + int(m.get("cacheCreationInputTokens", 0))
            for m in by_model.values()
        )
        tokens_out = sum(int(m.get("outputTokens", 0)) for m in by_model.values())
        tokens_cached = sum(int(m.get("cacheReadInputTokens", 0)) for m in by_model.values())
        return Usage(_cost_micros(result, by_model), tokens_in, tokens_out, tokens_cached)


def _cost_micros(result: dict[str, Any], by_model: dict[str, Any]) -> int | None:
    cost = result.get("total_cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, int | float) or cost < 0:
        return None
    # Docs: after a session crash every cost field may be zeroed, so zero there means unknown.
    if result.get("subtype") == "error_during_execution" and not by_model:
        return None
    return round(cost * MICROS_PER_USD)
