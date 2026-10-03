"""Headless worker: how one slice of a worker is launched.

Every flag here was verified by a recorded probe against CLI 2.1.285 unless marked otherwise.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from boss.ledger import Billing
from boss.redact import safe_text

CLI = "claude"
# From 2.1.277 a resumed session reports cumulative totals, which slice accounting depends on.
MIN_CLI_VERSION = (2, 1, 277)
WORKER_TOOLS = ("Read", "Write", "Edit")
SCHEMA_TOOL = "StructuredOutput"  # added by the CLI whenever --json-schema is set
# Path rules keep reads and writes inside the workspace; a bare `Write` wrote outside it (probe P5).
# No Bash: allowing even `pytest` lets a worker run any code it writes. The gate runs tests instead.
WORKER_TOOL_RULES = " ".join(f"{tool}(./**)" for tool in WORKER_TOOLS)
STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["done", "continuing", "blocked"]},
        "reason": {"type": "string"},
        # Checks the worker believes contradict the investor's request. Optional.
        "disputed_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"check": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["check", "reason"],
            },
        },
    },
    "required": ["status", "reason"],
}
MAX_DISPUTE_REASON_CHARS = 300
MAX_REASON_CHARS = 500
_STATUSES = frozenset(STATUS_SCHEMA["properties"]["status"]["enum"])
_ENV_ALLOWLIST = ("HOME", "PATH", "USER", "LANG", "TMPDIR", "CLAUDE_CONFIG_DIR")
_API_KEY_VAR = "ANTHROPIC_API_KEY"
_THINKING_VAR = "MAX_THINKING_TOKENS"  # read by the CLI; 0 turns extended thinking off


@dataclass(frozen=True, slots=True)
class SliceSpec:
    """One funded run of one worker. The first slice starts a session; later slices resume it."""

    session_id: UUID
    resume: bool
    prompt: str
    model: str
    cap_micros: int  # millionths of a US dollar, like the ledger
    append_system_prompt: str | None = None
    thinking_tokens: int | None = None  # None: the CLI's own default; 0 turns thinking off

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, UUID):
            raise ValueError("session_id must be a UUID")
        if not self.prompt.strip():
            raise ValueError("prompt must be non-empty")
        if self.prompt.startswith("-"):
            raise ValueError("prompt must not start with '-'; the CLI would read it as a flag")
        if not self.model:
            raise ValueError("model must be non-empty")
        if type(self.cap_micros) is not int or self.cap_micros <= 0:
            raise ValueError(f"cap_micros must be a positive int, got {self.cap_micros!r}")
        check_thinking(self.thinking_tokens)


def usd(micros: int) -> str:
    """Dollar string for the CLI, e.g. 300_000 -> "0.3", 6_000 -> "0.006"."""
    return f"{micros / 1_000_000:.6f}".rstrip("0").rstrip(".")


def uses_api_key(env: Mapping[str, str]) -> bool:
    return bool(env.get(_API_KEY_VAR))


def billing_mode(env: Mapping[str, str]) -> Billing:
    return Billing.API if uses_api_key(env) else Billing.SUBSCRIPTION


def worker_env(env: Mapping[str, str]) -> dict[str, str]:
    """Allowlisted environment for a worker: enough to find the CLI and its login, nothing else."""
    keep = [*_ENV_ALLOWLIST, _API_KEY_VAR] if uses_api_key(env) else _ENV_ALLOWLIST
    return {k: env[k] for k in keep if env.get(k)}


def check_thinking(tokens: int | None) -> None:
    if tokens is not None and (type(tokens) is not int or tokens < 0):
        raise ValueError(f"thinking tokens must be a non-negative int, got {tokens!r}")


def with_thinking(env: Mapping[str, str], tokens: int | None) -> dict[str, str]:
    """`env` with the CLI's thinking budget set. None leaves the CLI's own default."""
    check_thinking(tokens)
    if tokens is None:
        return dict(env)
    return {**env, _THINKING_VAR: str(tokens)}


def build_command(spec: SliceSpec, *, api_key: bool) -> list[str]:
    """Exact argv for one slice. Pure: no I/O, so the whole contract is pinned by a unit test."""
    # --bare needs an API key and skips all user config; --safe-mode does the same for a
    # subscription login (probe P2: no hooks, no MCP servers). kn: --bare not yet probed.
    isolation = "--bare" if api_key else "--safe-mode"
    session_flag = "--resume" if spec.resume else "--session-id"
    argv = [
        CLI, "--print", "--output-format", "stream-json", "--verbose", isolation,
        "--model", spec.model,
        "--tools", ",".join(WORKER_TOOLS),
        "--allowedTools", WORKER_TOOL_RULES,
        "--permission-mode", "dontAsk",
        "--max-budget-usd", usd(spec.cap_micros),
        "--json-schema", json.dumps(STATUS_SCHEMA, separators=(",", ":")),
        session_flag, str(spec.session_id),
    ]  # fmt: skip
    if spec.append_system_prompt:
        argv += ["--append-system-prompt", spec.append_system_prompt]
    return [*argv, spec.prompt]


def disputed_checks(status: Mapping[str, Any] | None, allowed: Collection[str]) -> dict[str, str]:
    """Check id -> reason for each check the worker disputes in its status report.

    The report is model output, so nothing in it is trusted: an entry that is malformed, repeats
    a check, gives no reason, or names a check outside `allowed` is dropped, and every reason is
    made safe to show and cut to a fixed length before it can reach the ledger.
    """
    raw = (status or {}).get("disputed_checks")
    found: dict[str, str] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        check, reason = item.get("check"), item.get("reason")
        if not isinstance(check, str) or check not in allowed or check in found:
            continue
        if isinstance(reason, str) and reason.strip():
            found[check] = _one_line(reason, MAX_DISPUTE_REASON_CHARS)
    return found


def _one_line(text: str, limit: int) -> str:
    """Model text for a one-line slot in the ledger and the report: newlines in it could forge
    lines of the report a person reads."""
    return safe_text(" ".join(text.split()), limit=limit)


def clean_status(status: object) -> dict[str, str] | None:
    """The worker's self-report reduced to what the ledger keeps: its status word, and its reason
    with secrets masked, control characters made visible and a bounded length. Everything else in
    the report is model output of unbounded size and is dropped. None when there is no report."""
    if not isinstance(status, dict):
        return None
    word, reason = status.get("status"), status.get("reason")
    return {
        "status": word if isinstance(word, str) and word in _STATUSES else "none",
        "reason": _one_line(reason, MAX_REASON_CHARS) if isinstance(reason, str) else "",
    }


class IsolationError(Exception):
    """The worker did not start in the configuration we launched. Never the worker's fault."""


def isolation_violations(
    init: Mapping[str, Any] | None,
    *,
    hook_events: int,
    expected_tools: Collection[str] = (*WORKER_TOOLS, SCHEMA_TOOL),
) -> list[str]:
    """Compare the CLI's `system/init` event with what we launched. Empty list = isolated.

    Plugins are not checked: under --safe-mode the CLI still lists installed plugins, but their
    hooks do not run (probe P2). Hooks are checked by counting hook events, which precede init.
    """
    if init is None:
        return ["no system/init event arrived"]
    problems: list[str] = []
    tools = init.get("tools")
    if not isinstance(tools, list):
        problems.append("init has no tools list")
    elif set(tools) != set(expected_tools):
        extra, missing = set(tools) - set(expected_tools), set(expected_tools) - set(tools)
        problems.append(f"tools differ: extra={sorted(extra)} missing={sorted(missing)}")
    if init.get("mcp_servers") != []:
        problems.append(f"MCP servers present: {init.get('mcp_servers')!r}")
    if init.get("permissionMode") != "dontAsk":
        problems.append(f"permission mode is {init.get('permissionMode')!r}, expected 'dontAsk'")
    if hook_events:
        problems.append(f"{hook_events} hook event(s) ran")
    version = parse_version(init.get("claude_code_version"))
    if version is None or version < MIN_CLI_VERSION:
        minimum = ".".join(map(str, MIN_CLI_VERSION))
        problems.append(f"CLI version {init.get('claude_code_version')!r} is below {minimum}")
    return problems


def require_isolation(
    init: Mapping[str, Any] | None,
    *,
    hook_events: int,
    expected_tools: Collection[str] = (*WORKER_TOOLS, SCHEMA_TOOL),
) -> None:
    problems = isolation_violations(init, hook_events=hook_events, expected_tools=expected_tools)
    if problems:
        raise IsolationError("; ".join(problems))


def parse_version(raw: object) -> tuple[int, ...] | None:
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", str(raw or ""))
    return tuple(int(part) for part in match.groups()) if match else None
