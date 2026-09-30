"""The boss's model calls. Each is one schema-validated call with no tools; code decides the rest.

The boss drafts, and code and the investor decide: money splits, file names and ids are computed
here, never taken from the model.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from boss.errors import Outcome, classify
from boss.stream import StreamReader, Usage
from boss.termsheet import CheckSpec, Round, Task, TermSheet, TermSheetError, as_list, validate
from boss.worker import CLI, usd, uses_api_key, with_thinking

TERM_SHEET_PROMPT = "term_sheet_v1.md"
MULTI_TASK_PROMPT = "term_sheet_v2.md"  # used when the boss may split the work
DEFAULT_MODEL = "haiku"
DEFAULT_CAP_MICROS = 250_000  # $0.25; live drafts cost $0.008-0.060, and a capped draft is wasted
DEFAULT_TIMEOUT_S = 300.0
MAX_CHECKS = 8


def draft_schema(max_tasks: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "minItems": 1,
                "maxItems": max_tasks,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "brief": {"type": "string"},
                        "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    },
                    "required": ["id", "brief", "paths"],
                },
            },
            "checks": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CHECKS,
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "task": {"type": "string"},
                        "code": {"type": "string"},
                    },
                    "required": ["description", "task", "code"],
                },
            },
        },
        "required": ["tasks", "checks"],
    }


DRAFT_SCHEMA = draft_schema(1)


class BossError(Exception):
    """A boss call did not produce usable output. Carries the outcome and usage for the ledger."""

    def __init__(self, message: str, outcome: Outcome, usage: Usage) -> None:
        super().__init__(message)
        self.outcome = outcome
        self.usage = usage


class InvalidDraftError(BossError):
    """The call succeeded and was paid for, but the draft does not validate as a term sheet."""

    def __init__(self, problems: list[str], usage: Usage) -> None:
        super().__init__(
            "draft term sheet is invalid: " + "; ".join(problems), Outcome.COMPLETED, usage
        )
        self.problems = problems


@dataclass(frozen=True, slots=True)
class Draft:
    sheet: TermSheet
    usage: Usage


def load_prompt(name: str) -> str:
    return (resources.files("boss") / "prompts" / name).read_text(encoding="utf-8")


def build_boss_command(
    *,
    prompt: str,
    system_prompt: str,
    schema: Mapping[str, Any],
    model: str,
    cap_micros: int,
    api_key: bool,
) -> list[str]:
    """Exact argv for a boss call: no tools, replaced system prompt, JSON-schema output."""
    return [
        CLI, "--print", "--output-format", "json", "--bare" if api_key else "--safe-mode",
        "--model", model,
        "--tools", "",
        "--system-prompt", system_prompt,
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--max-budget-usd", usd(cap_micros),
        prompt,
    ]  # fmt: skip


def draft_term_sheet(
    idea: str,
    budget_micros: int,
    checks_dir: Path,
    *,
    env: Mapping[str, str],
    model: str = DEFAULT_MODEL,
    cap_micros: int = DEFAULT_CAP_MICROS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    executable: str = CLI,
    max_tasks: int = 1,
    thinking_tokens: int | None = None,
) -> Draft:
    """Ask the boss for checks and up to max_tasks tasks; write the check files, return a sheet.

    `thinking_tokens` caps the model's extended thinking (0 turns it off). Thinking was most of a
    draft's cost in the pilot: four drafts averaged $0.086 with it and $0.031 without.

    Raises BossError if the call fails or returns unusable output, and InvalidDraftError (listing
    every problem) if the draft does not validate. Both carry the call's usage for the ledger.
    """
    if not idea.strip() or idea.lstrip().startswith("-"):
        raise ValueError("idea must be non-empty text that does not start with '-'")
    if max_tasks < 1:
        raise ValueError("max_tasks must be at least 1")
    prompt = f"Idea:\n{idea.strip()}"
    if max_tasks > 1:
        prompt += f"\n\nYou may use at most {max_tasks} tasks."
    argv = build_boss_command(
        prompt=prompt,
        system_prompt=load_prompt(MULTI_TASK_PROMPT if max_tasks > 1 else TERM_SHEET_PROMPT),
        schema=draft_schema(max_tasks),
        model=model,
        cap_micros=cap_micros,
        api_key=uses_api_key(env),
    )
    argv[0] = executable
    output = _call(argv, with_thinking(env, thinking_tokens), timeout_s)
    sheet = _sheet_from_output(output, idea.strip(), budget_micros, checks_dir, max_tasks)
    try:
        validate(sheet, checks_dir)
    except TermSheetError as exc:
        raise InvalidDraftError(exc.problems, output.usage()) from exc
    return Draft(sheet, output.usage())


def _call(argv: list[str], env: Mapping[str, str], timeout_s: float) -> StreamReader:
    with tempfile.TemporaryDirectory(prefix="boss_call_") as cwd:
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise BossError(
                f"boss call exceeded {timeout_s}s", Outcome.TIMEOUT, Usage(None, 0, 0, 0)
            ) from None
        except OSError as exc:
            # Never started, so nothing was spent, but we cannot prove it: cost stays unknown.
            raise BossError(
                f"cannot run {argv[0]!r} ({exc.strerror or exc}); run `boss doctor`",
                Outcome.CRASHED,
                Usage(None, 0, 0, 0),
            ) from exc
    reader = StreamReader()
    reader.feed(proc.stdout)
    outcome = classify(reader.signals())
    if outcome is not Outcome.COMPLETED:
        raise BossError(f"boss call ended as {outcome}", outcome, reader.usage())
    return reader


def _sheet_from_output(
    output: StreamReader, idea: str, budget_micros: int, checks_dir: Path, max_tasks: int
) -> TermSheet:
    draft = (output.result or {}).get("structured_output")
    if not isinstance(draft, dict):
        raise _unusable("no structured output", output)
    try:
        tasks = tuple(
            Task(t["id"], t["brief"], tuple(as_list(t["paths"]))) for t in as_list(draft["tasks"])
        )
        raw_checks = as_list(draft["checks"])
    except (KeyError, TypeError) as exc:
        raise _unusable(f"missing or malformed field: {exc}", output) from exc
    if not 1 <= len(tasks) <= max_tasks:
        wanted = "exactly one task" if max_tasks == 1 else f"1 to {max_tasks} tasks"
        raise _unusable(f"expected {wanted}, got {len(tasks)}", output)
    if not 1 <= len(raw_checks) <= MAX_CHECKS:
        raise _unusable(f"expected 1 to {MAX_CHECKS} checks, got {len(raw_checks)}", output)

    checks_dir.mkdir(parents=True, exist_ok=True)
    checks = []
    for n, raw in enumerate(raw_checks, start=1):
        check_id = f"c{n:02d}"  # ids and file names are ours, never the model's
        try:
            code, spec = (
                raw["code"],
                CheckSpec(check_id, raw["description"], f"test_{check_id}.py", raw["task"]),
            )
        except (KeyError, TypeError) as exc:
            raise _unusable(f"check {n} is malformed: {exc}", output) from exc
        if not isinstance(code, str):
            raise _unusable(f"check {n} code is not text", output)
        (checks_dir / spec.file).write_text(code, encoding="utf-8")
        checks.append(spec)
    # Stage 0: one round holding the whole budget, unlocked only when every check passes.
    rounds = (Round(1, budget_micros, len(checks)),)
    return TermSheet(idea, budget_micros, rounds, tuple(checks), tasks)


def _unusable(why: str, output: StreamReader) -> BossError:
    return BossError(f"unusable draft: {why}", Outcome.COMPLETED, output.usage())
