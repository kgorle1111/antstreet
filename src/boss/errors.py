"""Named outcomes for one headless worker run, classified from the CLI's stream signals.

Classification order matters: a failed login ends with `subtype: "success"` and `is_error: true`,
so `subtype` alone is never trusted (recorded with CLI 2.1.285).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    COMPLETED = "completed"  # the run ended normally; whether the work is done is the gate's call
    CAPPED = "capped"  # the slice budget was reached; a normal way for a slice to end
    MAX_TURNS = "max_turns"
    REFUSAL = "refusal"
    TIMEOUT = "timeout"  # we stopped it after the wall-clock limit
    CRASHED = "crashed"  # no usable result
    LOGIN = "login"
    RATE_LIMITED = "rate_limited"
    USAGE_LIMIT = "usage_limit"
    API_ERROR = "api_error"


# Never counted against a worker when deciding whether to fire it.
INFRASTRUCTURE = frozenset(
    {Outcome.LOGIN, Outcome.RATE_LIMITED, Outcome.USAGE_LIMIT, Outcome.API_ERROR}
)

_AUTH_ERRORS = frozenset({"authentication_failed", "oauth_org_not_allowed", "account_on_hold"})
_REFUSAL_SUBTYPES = frozenset({"refusal", "model_refusal"})
# kn: no recorded fixture for a plan usage limit yet;
# pattern adapted from Paperclip's Claude adapter. Replace with a recording when one occurs.
_USAGE_LIMIT_RE = re.compile(
    r"hit your (?:\w+ )?limit|usage limit reached|(?:5[- ]?hour|weekly) limit reached", re.I
)


@dataclass(frozen=True, slots=True)
class RunSignals:
    result: Mapping[str, Any] | None  # the final `result` event, or None if none arrived
    retry_errors: tuple[str, ...] = ()  # `error` field of each `system/api_retry` event, in order
    rate_limit_status: str | None = None  # `status` of the last `rate_limit_event`
    timed_out: bool = False


def classify(signals: RunSignals) -> Outcome:
    if signals.timed_out:
        return Outcome.TIMEOUT
    result = signals.result
    if result is None:
        return Outcome.CRASHED

    subtype = str(result.get("subtype", ""))
    terminal = str(result.get("terminal_reason", ""))
    if subtype == "error_max_budget_usd" or terminal == "budget_exhausted":
        return Outcome.CAPPED
    if subtype == "error_max_turns":
        return Outcome.MAX_TURNS
    if subtype in _REFUSAL_SUBTYPES or result.get("stop_reason") == "refusal":
        return Outcome.REFUSAL
    if not result.get("is_error"):
        return Outcome.COMPLETED
    return _classify_error(result, signals)


def _classify_error(result: Mapping[str, Any], signals: RunSignals) -> Outcome:
    status = result.get("api_error_status")
    retries = set(signals.retry_errors)
    text = str(result.get("result") or "") + " " + " ".join(map(str, result.get("errors") or ()))
    if status in (401, 403) or retries & _AUTH_ERRORS:
        return Outcome.LOGIN
    if signals.rate_limit_status == "rejected" or _USAGE_LIMIT_RE.search(text):
        return Outcome.USAGE_LIMIT
    if status == 429 or "rate_limit" in retries:
        return Outcome.RATE_LIMITED
    if status is not None or result.get("terminal_reason") == "api_error":
        return Outcome.API_ERROR
    return Outcome.CRASHED
