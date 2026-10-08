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
    SESSION_LOST = "session_lost"  # the session to resume is gone from the CLI's store


# Never counted against a worker when deciding whether to fire it.
INFRASTRUCTURE = frozenset(
    {
        Outcome.LOGIN,
        Outcome.RATE_LIMITED,
        Outcome.USAGE_LIMIT,
        Outcome.API_ERROR,
        Outcome.SESSION_LOST,
    }
)

_AUTH_ERRORS = frozenset({"authentication_failed", "oauth_org_not_allowed", "account_on_hold"})
_REFUSAL_SUBTYPES = frozenset({"refusal", "model_refusal"})
# kn: no recorded fixture for a plan usage limit yet;
# pattern adapted from Paperclip's Claude adapter. Replace with a recording when one occurs.
_USAGE_LIMIT_RE = re.compile(
    r"hit your (?:\w+ )?limit|usage limit reached|(?:5[- ]?hour|weekly) limit reached", re.I
)


# Probe (CLI 2.1.285): resuming a session that was never created answers "No conversation found".
# Not recorded as a fixture, so which stream carries it (stderr, or a result's text) is not known:
# both are read.
_SESSION_GONE_RE = re.compile(r"No conversation found", re.I)


@dataclass(frozen=True, slots=True)
class RunSignals:
    result: Mapping[str, Any] | None  # the final `result` event, or None if none arrived
    retry_errors: tuple[str, ...] = ()  # `error` field of each `system/api_retry` event, in order
    rate_limit_status: str | None = None  # `status` of the last `rate_limit_event`
    timed_out: bool = False
    stderr_tail: str = ""  # the CLI's own stderr, already redacted
    # `error` of each assistant event flagged `is_api_error_message`. From CLI 2.1.292 a login
    # whose OAuth refresh fails reports only here: no retry, no status (recorded 2026-10-07).
    message_errors: tuple[str, ...] = ()


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    """The text in a field that should be a list of strings; a lone string counts as one entry."""
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list | tuple) else []


def classify(signals: RunSignals) -> Outcome:
    """Never raises: a field of the wrong type reads as absent, and no verdict is not success."""
    if signals.timed_out:
        return Outcome.TIMEOUT
    result = signals.result
    if not isinstance(result, Mapping):
        return (
            Outcome.SESSION_LOST
            if _SESSION_GONE_RE.search(signals.stderr_tail)
            else Outcome.CRASHED
        )

    subtype = _str(result.get("subtype"))
    terminal = _str(result.get("terminal_reason"))
    if subtype == "error_max_budget_usd" or terminal == "budget_exhausted":
        return Outcome.CAPPED
    if subtype == "error_max_turns":
        return Outcome.MAX_TURNS
    if subtype in _REFUSAL_SUBTYPES or result.get("stop_reason") == "refusal":
        return Outcome.REFUSAL
    if result.get("is_error") is False:  # missing or non-bool is unknown, so not COMPLETED
        return Outcome.COMPLETED
    return _classify_error(result, signals)


def _classify_error(result: Mapping[str, Any], signals: RunSignals) -> Outcome:
    raw_status = result.get("api_error_status")
    status = raw_status if type(raw_status) is int else None
    retries = set(_strings(signals.retry_errors)) | set(_strings(signals.message_errors))
    text = " ".join([_str(result.get("result")), *_strings(result.get("errors"))])
    if _SESSION_GONE_RE.search(text) or _SESSION_GONE_RE.search(signals.stderr_tail):
        return Outcome.SESSION_LOST
    if status in (401, 403) or retries & _AUTH_ERRORS:
        return Outcome.LOGIN
    if signals.rate_limit_status == "rejected" or _USAGE_LIMIT_RE.search(text):
        return Outcome.USAGE_LIMIT
    if status == 429 or "rate_limit" in retries:
        return Outcome.RATE_LIMITED
    if status is not None or _str(result.get("terminal_reason")) == "api_error":
        return Outcome.API_ERROR
    return Outcome.CRASHED
