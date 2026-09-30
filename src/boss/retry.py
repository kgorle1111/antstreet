"""What to do about a run that failed for reasons that are not the worker's fault.

Pure decisions only: nothing here sleeps, reads a clock or touches a process. The caller acts on
the returned `Action`. `rate_limit` is the CLI's latest `rate_limit_info`, which may be missing or
malformed, so every read of it is defensive and never raises.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from boss.errors import INFRASTRUCTURE, Outcome


@dataclass(frozen=True, slots=True)
class Wait:
    seconds: float
    reason: str


@dataclass(frozen=True, slots=True)
class Pause:
    until_epoch: float | None  # None = reset time unknown; the run stops and is resumed by hand
    reason: str


@dataclass(frozen=True, slots=True)
class GiveUp:
    reason: str
    fix: str  # one-line next step for the user


Action = Wait | Pause | GiveUp

_MAX_DOUBLINGS = 1000  # 2.0 ** 1024 overflows; every sane cap_s is reached long before this


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _windows(rate_limit: Mapping[str, Any] | None) -> list[tuple[str, float, float]]:
    """(name, utilization, resetsAt) for each window with both well formed and resetsAt > 0."""
    raw = rate_limit.get("unifiedWindows") if isinstance(rate_limit, Mapping) else None
    if not isinstance(raw, Mapping):
        return []
    found = []
    for name, window in raw.items():
        if not isinstance(window, Mapping):
            continue
        utilization = _number(window.get("utilization"))
        resets_at = _number(window.get("resetsAt"))
        if utilization is not None and resets_at is not None and resets_at > 0:
            found.append((str(name), utilization, resets_at))
    return found


def _usage_limit_reset(rate_limit: Mapping[str, Any] | None) -> float | None:
    top = _number(rate_limit.get("resetsAt")) if isinstance(rate_limit, Mapping) else None
    if top is not None and top > 0:
        return top
    saturated = [r for _, utilization, r in _windows(rate_limit) if utilization >= 1.0]
    return min(saturated, default=None)


def infra_action(
    outcome: Outcome,
    attempt: int,
    rate_limit: Mapping[str, Any] | None,
    *,
    max_attempts: int = 4,
    base_s: float = 5.0,
    cap_s: float = 120.0,
    jitter: Callable[[], float] = random.random,
) -> Action:
    """`attempt` is 1 for the first failure. Backoff is exponential with equal jitter."""
    if outcome not in INFRASTRUCTURE:
        raise ValueError(f"{outcome!r} is not an infrastructure outcome")
    if attempt < 1:
        raise ValueError(f"attempt starts at 1, got {attempt}")

    if outcome is Outcome.LOGIN:
        return GiveUp("the CLI is not logged in", "run `claude auth login`, then resume")
    if outcome is Outcome.USAGE_LIMIT:
        return Pause(_usage_limit_reset(rate_limit), "plan usage limit reached")
    if attempt > max_attempts:
        fix = (
            "try again later"
            if outcome is Outcome.RATE_LIMITED
            else "check the provider status page, then try again"
        )
        return GiveUp(f"{outcome.value} on all {max_attempts} attempts", fix)
    delay = min(cap_s, base_s * 2.0 ** min(attempt - 1, _MAX_DOUBLINGS))
    seconds = delay / 2 + (delay / 2) * jitter()
    return Wait(seconds, f"{outcome.value}, attempt {attempt} of {max_attempts}")


def plan_pressure(rate_limit: Mapping[str, Any] | None, *, threshold: float = 0.9) -> Pause | None:
    """Pause before a plan window runs out; the window that resets latest decides.

    `utilization` is a fraction (recorded CLI 2.1.285: 0.08, 0.11). A value outside 0..1 means the
    scale is not what we assume, so that window is unknown: neither pressure nor zero.
    """
    over = [w for w in _windows(rate_limit) if max(0.0, threshold) <= w[1] <= 1]
    if not over:
        return None
    name, utilization, resets_at = max(over, key=lambda w: w[2])
    return Pause(resets_at, f"{name} window at {utilization:.0%} of the plan limit")
