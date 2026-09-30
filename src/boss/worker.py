"""Headless worker: how one slice of a worker is launched.

Every flag here was verified by a recorded probe against CLI 2.1.285 unless marked otherwise.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from boss.ledger import Billing

CLI = "claude"
WORKER_TOOLS = ("Read", "Write", "Edit")
# Path rules keep reads and writes inside the workspace; a bare `Write` wrote outside it (probe P5).
# No Bash: allowing even `pytest` lets a worker run any code it writes. The gate runs tests instead.
WORKER_TOOL_RULES = " ".join(f"{tool}(./**)" for tool in WORKER_TOOLS)
STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["done", "continuing", "blocked"]},
        "reason": {"type": "string"},
    },
    "required": ["status", "reason"],
}
_ENV_ALLOWLIST = ("HOME", "PATH", "USER", "LANG", "TMPDIR", "CLAUDE_CONFIG_DIR")
_API_KEY_VAR = "ANTHROPIC_API_KEY"


@dataclass(frozen=True, slots=True)
class SliceSpec:
    """One funded run of one worker. The first slice starts a session; later slices resume it."""

    session_id: UUID
    resume: bool
    prompt: str
    model: str
    cap_micros: int  # millionths of a US dollar, like the ledger
    append_system_prompt: str | None = None

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
