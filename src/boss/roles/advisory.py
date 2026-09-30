"""An advisory role that gives the investor an opinion on the boss's checks.

The check auditor answers one question for every check of a draft before approval: does
this check demand something the idea does not state? Its opinion is grounded (it must quote
the idea word for word, checked by code), shown to the investor marked as an opinion, and
decides nothing. `boss.bench.audit` scores it against ground truth: the task's reference
solution fails a check that is wrong.

Check code and descriptions are the boss's output, so they go into the prompt inside a
fence they cannot close.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.redact import safe_text
from boss.roles.base import RoleOutputError, RoleSpec, call_role
from boss.roles.stories import is_fragment
from boss.stream import Usage
from boss.termsheet import CheckSpec
from boss.worker import CLI

CONSISTENT, CONTRADICTS, UNSUPPORTED = "consistent", "contradicts", "unsupported"
VERDICTS = (CONSISTENT, CONTRADICTS, UNSUPPORTED)
_SHOWN_QUOTE_CHARS = 240
_SHOWN_WHY_CHARS = 240
_VERDICT_KEYS = ("check", "verdict", "quote", "why")
_FILE = re.compile(r"[A-Za-z0-9_.-]+\Z")
_LABELS = {
    CONSISTENT: "consistent with the idea",
    CONTRADICTS: "contradicts the idea",
    UNSUPPORTED: "not stated in the idea",
}
_TEXT = {"type": "string"}

AUDITOR = RoleSpec(
    name="check_auditor",
    department="advisory",
    reports_to="boss",
    purpose="an opinion, per check, on whether the idea states what the check demands",
    gate=(
        "exactly one verdict per check and no others, each from the allowed set, with a quote "
        "that is a fragment of the idea wherever one is required"
    ),
    prompt="check_auditor_v1.md",
    skills=(
        "check_auditor/trace-expected-values",
        "check_auditor/invented-rules",
        "check_auditor/quoting",
    ),
)
SPECS = (AUDITOR,)


def audit_schema(check_ids: Sequence[str]) -> dict[str, Any]:
    """One verdict per check id: the schema pins the count and the ids, the gate still checks."""
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": len(check_ids),
                "maxItems": len(check_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "check": {"type": "string", "enum": list(check_ids)},
                        "verdict": {"type": "string", "enum": list(VERDICTS)},
                        "quote": _TEXT,
                        "why": {"type": "string", "minLength": 1},
                    },
                    "required": ["check", "verdict", "quote", "why"],
                },
            }
        },
        "required": ["verdicts"],
    }


@dataclass(frozen=True, slots=True)
class Verdict:
    check: str  # a check id from the draft
    verdict: str  # one of VERDICTS
    quote: str  # a fragment of the idea, word for word; may be empty only for "unsupported"
    why: str


@dataclass(frozen=True, slots=True)
class Audit:
    verdicts: tuple[Verdict, ...]

    @property
    def flagged(self) -> tuple[Verdict, ...]:
        """The checks the auditor thinks the idea does not back: contradicted or unsupported."""
        return tuple(v for v in self.verdicts if v.verdict != CONSISTENT)


class AdvisoryError(ValueError):
    """The data is not shaped like an audit at all (as opposed to one with problems)."""


def parse_audit(data: object) -> Audit:
    """Build an Audit from schema-shaped data; whether it is any good is `audit_problems`' job."""
    try:
        if not isinstance(data, Mapping):
            raise TypeError("not an object")
        verdicts = _items(data, "verdicts")
        return Audit(tuple(Verdict(*(_text(v, k) for k in _VERDICT_KEYS)) for v in verdicts))
    except (KeyError, TypeError) as exc:
        raise AdvisoryError(f"not shaped like an audit: {exc}") from exc


def audit_problems(audit: Audit, idea: str, check_ids: Sequence[str]) -> list[str]:
    """Everything wrong with an audit, one line each. Empty means it passes the gate."""
    problems: list[str] = []
    seen = Counter(v.check for v in audit.verdicts)
    for check_id in check_ids:
        if seen[check_id] == 0:
            problems.append(f"{check_id}: no verdict")
        elif seen[check_id] > 1:
            problems.append(f"{check_id}: {seen[check_id]} verdicts, needs exactly one")
    for other in sorted(set(seen) - set(check_ids)):
        problems.append(f"verdict for {_line(other, 40)!r}, which is not a check of this draft")
    for v in audit.verdicts:
        name = _line(v.check, 40)
        if v.verdict not in VERDICTS:
            problems.append(f"{name}: verdict must be one of {', '.join(VERDICTS)}")
        elif v.verdict == UNSUPPORTED and not v.quote.strip():
            pass  # nothing relevant to quote is a legitimate answer
        else:
            problems += _quote_problems(name, v.quote, idea)
        if not v.why.strip():
            problems.append(f"{name}: why is empty")
    return problems


def audit_checks(
    idea: str,
    checks: Sequence[CheckSpec],
    checks_dir: Path,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> tuple[Audit, Usage]:
    """One call: the auditor's opinion on every check of one draft, in the checks' order.

    Check code is read from `checks_dir / check.file`. Raises RoleError when the call fails and
    RoleOutputError (with the usage) when its output fails the gate; the caller books the spend.
    """
    if not idea.strip():
        raise ValueError("an audit needs the idea")
    if not checks:
        raise ValueError("an audit needs at least one check")
    ids = [c.id for c in checks]
    if len(set(ids)) != len(ids):
        raise ValueError(f"check ids must be unique, got {ids}")
    sections = [_block("The idea, in the investor's words:", idea.strip())]
    for check in checks:
        sections.append(_check_section(check, checks_dir))
    prompt = "Audit these checks against the idea.\n\n" + "\n\n".join(sections)
    output = call_role(
        AUDITOR,
        prompt,
        audit_schema(ids),
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
        timeout_s=timeout_s,
    )
    try:
        audit = parse_audit(output.data)
    except AdvisoryError as exc:
        raise RoleOutputError(AUDITOR.name, [str(exc)], output.usage) from exc
    if problems := audit_problems(audit, idea, ids):
        raise RoleOutputError(AUDITOR.name, problems, output.usage)
    by_id = {v.check: v for v in audit.verdicts}
    return Audit(tuple(by_id[i] for i in ids)), output.usage


def render_verdict(verdict: Verdict) -> str:
    """One line for the investor next to a check. Model text passes `safe_text` on one line."""
    parts = [
        f"{_line(verdict.check, 40)}: auditor's opinion, unverified: "
        f"{_LABELS.get(verdict.verdict) or _line(verdict.verdict, 40)}"
    ]
    if verdict.quote.strip():
        parts.append(f'idea: "{_line(verdict.quote, _SHOWN_QUOTE_CHARS)}"')
    parts.append(f"why: {_line(verdict.why, _SHOWN_WHY_CHARS)}")
    return " | ".join(parts)


def render_audit(audit: Audit) -> str:
    """One line per check, in order."""
    return "\n".join(render_verdict(v) for v in audit.verdicts)


def _quote_problems(name: str, quote: str, idea: str) -> list[str]:
    if is_fragment(quote, idea):
        return []
    return [f"{name}: quote must be a fragment of the idea, word for word: {_line(quote, 80)!r}"]


def _check_section(check: CheckSpec, checks_dir: Path) -> str:
    if not _FILE.fullmatch(check.file) or check.file.startswith("."):
        raise ValueError(f"check {check.id}: {check.file!r} is not a plain file name")
    path = checks_dir / check.file
    if not path.is_file():
        raise ValueError(f"check {check.id}: no file {path}")
    return "\n".join(
        [
            f"Check {check.id}",
            _block("Description (the boss's words):", check.description.strip() or "(none saved)"),
            _block("Code:", path.read_text(encoding="utf-8")),
        ]
    )


def _block(label: str, text: str) -> str:
    """`text` under a label in a fence longer than any run of backticks inside it."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{label}\n{fence}\n{text}\n{fence}"


def _line(text: str, limit: int) -> str:
    return safe_text(" ".join(text.split()), limit=limit)


def _text(item: object, key: str) -> str:
    value = item[key]  # type: ignore[index]
    if not isinstance(value, str):
        raise TypeError(f"{key} is not text")
    return value


def _items(item: Mapping[str, Any], key: str) -> list[Any]:
    value = item[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} is not a list")
    return value
