"""The spec mapper: which rules of the idea does each check assert? One call, advisory.

It reads the rules (the idea's own sentences, numbered by `boss.spec`) and each check's code with
line numbers, and nothing else: not the boss's description of the check, not the rules the boss
says it covers, not the file name. Its output is data until the gate here has run: every check
mapped exactly once, every rule id one of the idea's, every line inside the check and on an
assertion (an `assert`, or the `raises` that expects an error). It writes no code and no prose;
what it says is shown as ids and numbers built by code, and it changes nothing: the coverage the
investor sees and approves is computed from the checks alone (`boss.spec.verify`).

Why it exists: a boss that cites a rule it does not assert is the failure the deterministic check
cannot see when the rule names nothing concrete. A second reader of the same code, kept blind to
the claim, can disagree with it. It is the same kind of model reading the same words, so it
catches a careless claim, not a shared misreading.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss import spec
from boss.redact import safe_text
from boss.roles.advisory import _block
from boss.roles.base import RoleOutputError, RoleSpec, call_role
from boss.stream import Usage
from boss.termsheet import CheckSpec
from boss.worker import CLI

MAX_EXERCISES = 12  # per check; a check that exercises more than this is not one behaviour
_ASSERTING_CALLS = frozenset({"raises", "warns", "assertRaises", "assertWarns"})
_FILE = re.compile(r"[A-Za-z0-9_.-]+\Z")

SPEC_MAPPER = RoleSpec(
    name="spec_mapper",
    department="quality",
    reports_to="boss",
    purpose="says which rules of the idea each check asserts, from the check's code alone",
    gate=(
        "exactly one entry per check and no others, every rule an id of the idea, every line "
        "inside the check and on an assertion"
    ),
    prompt="spec_mapper_v1.md",
)
SPECS = (SPEC_MAPPER,)


@dataclass(frozen=True, slots=True)
class RuleMap:
    """What the mapper found: for each check, the (rule, line) pairs it says are asserted."""

    exercises: Mapping[str, tuple[tuple[str, int], ...]]

    def rules_of(self, check: str) -> set[str]:
        return {rule for rule, _ in self.exercises.get(check, ())}


@dataclass(frozen=True, slots=True)
class Comparison:
    overclaims: tuple[tuple[str, str], ...]  # (check, rule): the boss cites it, no assertion found
    unclaimed: tuple[tuple[str, str], ...]  # (check, rule): asserted, not cited (harmless)


def mapper_schema(check_ids: Sequence[str]) -> dict[str, Any]:
    """One entry per check id: the schema pins the count and the ids, the gate still checks."""
    return {
        "type": "object",
        "properties": {
            "maps": {
                "type": "array",
                "minItems": len(check_ids),
                "maxItems": len(check_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "check": {"type": "string", "enum": list(check_ids)},
                        "exercises": {
                            "type": "array",
                            "maxItems": MAX_EXERCISES,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "rule": {"type": "string"},
                                    "line": {"type": "integer", "minimum": 1},
                                },
                                "required": ["rule", "line"],
                            },
                        },
                    },
                    "required": ["check", "exercises"],
                },
            }
        },
        "required": ["maps"],
    }


def assertion_lines(source: str) -> set[int] | None:
    """The lines a check asserts on: every line of an `assert` statement, and of a call to
    `raises` or `warns`. None when the source does not parse."""
    try:
        tree = ast.parse(source.lstrip("﻿"))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        elif isinstance(node, ast.Call):
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if name in _ASSERTING_CALLS:
                lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def map_problems(
    data: object, rule_ids: set[str], sources: Mapping[str, str]
) -> tuple[RuleMap | None, list[str]]:
    """The map in `data`, or every way it is not one."""
    items = data.get("maps") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None, ["maps is not a list"]
    problems: list[str] = []
    found: dict[str, tuple[tuple[str, int], ...]] = {}
    asserted = {c: assertion_lines(src) for c, src in sources.items()}
    for n, item in enumerate(items, start=1):
        check = item.get("check") if isinstance(item, dict) else None
        raw = item.get("exercises") if isinstance(item, dict) else None
        if not isinstance(check, str) or not isinstance(raw, list):
            problems.append(f"entry {n}: needs a text check and a list of exercises")
            continue
        if check not in sources:
            problems.append(f"entry {n}: {check!r} is not a check")
            continue
        if check in found:
            problems.append(f"{check} is mapped twice")
            continue
        pairs: dict[tuple[str, int], None] = {}
        for ex in raw[: MAX_EXERCISES + 1]:
            rule, line = (ex.get("rule"), ex.get("line")) if isinstance(ex, dict) else (None, None)
            if not isinstance(rule, str) or type(line) is not int:
                problems.append(f"{check}: an exercise needs a text rule and a whole line number")
            elif rule not in rule_ids:
                problems.append(f"{check}: {rule!r} is not a rule of the idea")
            elif asserted[check] is None:
                problems.append(f"{check}: does not parse, so no line of it can be asserted on")
            elif line not in (asserted[check] or ()):
                problems.append(f"{check}: line {line} is not an assertion")
            else:
                pairs[(rule, line)] = None
        if len(raw) > MAX_EXERCISES:
            problems.append(f"{check}: more than {MAX_EXERCISES} exercises")
        found[check] = tuple(pairs)
    problems += [f"check {c} has no entry" for c in sources if c not in found]
    return (None if problems else RuleMap(found)), problems


def compare(claims: Mapping[str, Sequence[str]], mapped: RuleMap) -> Comparison:
    """The boss's claims against the mapper's map. Pure; neither side is trusted by it."""
    over, unclaimed = [], []
    for check, cited in claims.items():
        seen = mapped.rules_of(check)
        over += [(check, rule) for rule in dict.fromkeys(cited) if rule not in seen]
        unclaimed += [(check, rule) for rule in sorted(seen) if rule not in cited]
    return Comparison(tuple(over), tuple(unclaimed))


def render_comparison(comparison: Comparison, rules: spec.Split) -> str:
    """The investor's note: ids and counts built by code, the idea's own words for each rule."""
    by_id = rules.by_id()
    lines = [
        "Spec mapper's opinion (advisory: it read the check code and the rules, never what the "
        "boss says each check covers; the same kind of model, so it can share a misreading):"
    ]
    if not comparison.overclaims:
        lines.append("  Every rule a check cites, the mapper also found asserted in it.")
    else:
        lines.append("  CITED, BUT NO ASSERTION FOUND (the check may not test what it claims):")
        for check, rule in comparison.overclaims:
            text = " ".join(by_id[rule].text.split()) if rule in by_id else ""
            lines.append(f"    {rule} -> {check}: {safe_text(text, limit=120)}")
    if comparison.unclaimed:
        found = ", ".join(f"{check} asserts {rule}" for check, rule in comparison.unclaimed)
        lines.append(f"  Asserted but not cited (harmless): {found}")
    return "\n".join(lines)


def map_rules(
    rules: spec.Split,
    checks: Sequence[CheckSpec],
    checks_dir: Path,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> tuple[RuleMap, Usage]:
    """One call: which rules each check asserts. The prompt holds the scored rules and each check's
    id and code (numbered lines); never the check's description, file name or cited rules.

    Raises ValueError before any call for no rules or no checks, RoleError when the call fails and
    RoleOutputError (with the usage) when its output fails the gate; the caller books the spend.
    """
    if not rules.scorable:
        raise ValueError("the mapper needs at least one scored rule")
    if not checks:
        raise ValueError("the mapper needs at least one check")
    sources: dict[str, str] = {}
    for check in checks:
        if not _FILE.fullmatch(check.file) or check.file.startswith("."):
            raise ValueError(f"check {check.id}: {check.file!r} is not a plain file name")
        path = checks_dir / check.file
        if not path.is_file():
            raise ValueError(f"check {check.id}: no file {path}")
        sources[check.id] = path.read_text(encoding="utf-8")
    listed = "\n".join(f"{r.id}: {' '.join(r.text.split())}" for r in rules.scorable)
    sections = [_block("The rules:", listed)]
    for check_id, source in sources.items():
        numbered = "\n".join(f"{n}| {line}" for n, line in enumerate(source.splitlines(), start=1))
        sections.append(_block(f"Check {check_id}:", numbered))
    ids = list(sources)
    output = call_role(
        SPEC_MAPPER,
        "Map each check to the rules it asserts.\n\n" + "\n\n".join(sections),
        mapper_schema(ids),
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
        timeout_s=timeout_s,
    )
    mapped, problems = map_problems(output.data, {r.id for r in rules.scorable}, sources)
    if mapped is None:
        raise RoleOutputError(SPEC_MAPPER.name, problems, output.usage, output.data)
    return mapped, output.usage
