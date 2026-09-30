"""What every specialist role is: one structured model call with no tools.

A role drafts; it never decides. Its output is data that must pass the deterministic gate named
in its spec before anything uses it, its spend is a ledger event like everyone else's, and it is
off unless the investor turns it on. A role that needs to touch files is not a role: it is a
worker, and workers already exist.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from boss.boss import BossError, _call, build_boss_command, load_prompt
from boss.errors import Outcome
from boss.ledger import Billing, EventType
from boss.skills import load_skill
from boss.stream import Usage
from boss.worker import CLI, billing_mode, uses_api_key, with_thinking

DEPARTMENTS = ("product", "engineering", "quality", "delivery", "advisory")
DEFAULT_ROLE_CAP_MICROS = 150_000
_NAME = re.compile(r"[a-z][a-z_]{1,30}")


@dataclass(frozen=True, slots=True)
class RoleSpec:
    name: str  # also its ledger actor: role:<name>
    department: str  # one of DEPARTMENTS
    reports_to: str  # "boss", or another role's name
    purpose: str  # one line: what it produces
    gate: str  # one line: the deterministic check its output must pass before it is used
    prompt: str  # a file under prompts/, versioned like every prompt
    skills: tuple[str, ...] = ()  # skill ids appended to its system prompt, in order
    cap_micros: int = DEFAULT_ROLE_CAP_MICROS  # budget for one call
    default_on: bool = False  # a role is off until a measurement says it earns its cost

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ValueError(f"role name must be lower_snake_case, got {self.name!r}")
        if self.department not in DEPARTMENTS:
            raise ValueError(f"department must be one of {DEPARTMENTS}, got {self.department!r}")
        if not self.purpose.strip() or not self.gate.strip():
            raise ValueError(f"role {self.name} needs a purpose and a gate")
        if type(self.cap_micros) is not int or self.cap_micros <= 0:
            raise ValueError(f"cap_micros must be a positive int, got {self.cap_micros!r}")

    @property
    def actor(self) -> str:
        return f"role:{self.name}"


class RoleError(Exception):
    """A role's call did not produce usable output. Carries what the ledger needs."""

    def __init__(self, role: str, message: str, outcome: Outcome, usage: Usage) -> None:
        super().__init__(f"{role}: {message}")
        self.role, self.outcome, self.usage = role, outcome, usage


class RoleOutputError(RoleError):
    """The call was paid for and its output failed the role's gate. Lists every problem, and
    keeps the refused output: it was paid for, and it is the evidence when a gate is wrong."""

    def __init__(
        self, role: str, problems: list[str], usage: Usage, data: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            role, "output failed its gate: " + "; ".join(problems), Outcome.COMPLETED, usage
        )
        self.problems = problems
        self.data = data


@dataclass(frozen=True, slots=True)
class RoleOutput:
    data: dict[str, Any]  # schema-shaped, not yet gated
    usage: Usage


def system_prompt(spec: RoleSpec) -> str:
    """The role's prompt followed by each of its skills, in the order the spec lists them."""
    parts = [load_prompt(spec.prompt).rstrip()]
    parts += [load_skill(skill).text.rstrip() for skill in spec.skills]
    return "\n\n".join(parts) + "\n"


def call_role(
    spec: RoleSpec,
    user_prompt: str,
    schema: Mapping[str, Any],
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> RoleOutput:
    """One call: no tools, the role's system prompt, schema-validated output.

    Raises RoleError when the call fails or returns nothing usable; the caller records the
    spend either way (`ledger_fields`). The output is shaped by the schema and nothing more:
    the caller must run the role's gate on it.
    """
    if not user_prompt.strip() or user_prompt.lstrip().startswith("-"):
        raise ValueError("a role's prompt must be non-empty text that does not start with '-'")
    argv = build_boss_command(
        prompt=user_prompt,
        system_prompt=system_prompt(spec),
        schema=schema,
        model=model,
        cap_micros=spec.cap_micros,
        api_key=uses_api_key(env),
    )
    argv[0] = executable
    try:
        reader = _call(argv, with_thinking(env, thinking_tokens), timeout_s)
    except BossError as exc:
        raise RoleError(spec.name, str(exc), exc.outcome, exc.usage) from exc
    data = (reader.result or {}).get("structured_output")
    if not isinstance(data, dict):
        raise RoleError(spec.name, "no structured output", Outcome.COMPLETED, reader.usage())
    return RoleOutput(data, reader.usage())


def ledger_fields(
    spec: RoleSpec, usage: Usage, outcome: str, *, model: str, env: Mapping[str, str], **data: Any
) -> dict[str, Any]:
    """Keyword arguments for a Recorder call that books a role's spend:
    `record(spec.actor, EventType.ROLE_CALL, **ledger_fields(...))`."""
    billing: Billing = billing_mode(env)
    return {
        "cost_micros": usage.cost_micros,
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "tokens_cached": usage.tokens_cached,
        "billing": billing,
        "data": {
            "role": spec.name,
            "model": model,
            "prompt": spec.prompt,
            "skills": list(spec.skills),
            "outcome": outcome,
            **data,
        },
    }


ROLE_CALL = EventType.ROLE_CALL
