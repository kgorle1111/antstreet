"""The judge: scores an artifact that cannot be checked by running it, against a rubric, and
quotes the evidence for every score.

A judgement is ADVISORY. It is labelled `uncalibrated` until a calibration file shows the same
judge (rubric id and version, model, prompt and skills) agreeing with a person on enough cases,
and nothing in the firm may gate on an uncalibrated judgement. Any code path that acts on a score
must call `require_calibrated` first; `Judgement.calibrated` is set by `judge_artifact` alone.

The judge drafts a score; the gate below is pure code: every criterion scored once, integer
scores from 1 to 5, and every piece of evidence a fragment of the artifact. Grounding beats
begging: a score with no quote from the artifact is not accepted.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from boss.redact import safe_text
from boss.roles.base import RoleOutputError, RoleSpec, call_role
from boss.roles.stories import normalise
from boss.stream import Usage
from boss.worker import CLI

MIN_SCORE, MAX_SCORE = 1, 5
ANCHOR_POINTS = ("1", "3", "5")  # what a 1, a 3 and a 5 look like; 2 and 4 sit between
MIN_CRITERIA, MAX_CRITERIA = 3, 5  # fewer cannot separate faults; more dilutes each score
MIN_EVIDENCE_CHARS = 8  # shorter fragments match an artifact by accident
_ID = re.compile(r"[a-z][a-z0-9_]{1,30}")
_SHOWN_CHARS = 120

JUDGE = RoleSpec(
    name="judge",
    department="quality",
    reports_to="boss",
    purpose="scores an artifact against a rubric and quotes the evidence for each score",
    gate="every criterion scored once, integer 1 to 5, each backed by a fragment of the artifact",
    prompt="judge_v1.md",
    skills=("judge/anchored-scoring", "judge/known-judge-biases"),
)
SPECS = (JUDGE,)

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_CRITERIA,
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "score": {"type": "integer", "minimum": MIN_SCORE, "maximum": MAX_SCORE},
                    "evidence": {"type": "string", "minLength": 1},
                },
                "required": ["criterion", "score", "evidence"],
            },
        },
        "summary": {"type": "string", "minLength": 1},
    },
    "required": ["scores", "summary"],
}


class RubricError(ValueError):
    """A rubric file is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    question: str  # one line
    anchors: tuple[str, str, str]  # what a 1, a 3 and a 5 look like


@dataclass(frozen=True, slots=True)
class Rubric:
    id: str  # also the file name: rubrics/<id>.json
    version: int  # bump it whenever the wording changes: calibrations are tied to it
    title: str
    criteria: tuple[Criterion, ...]


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """`object_pairs_hook` for json: a repeated key is an error, not a silent last-one-wins."""
    keys = [key for key, _ in pairs]
    for key in keys:
        if keys.count(key) > 1:
            raise ValueError(f"key {key!r} appears more than once")
    return dict(pairs)


def load_rubric(rubric_id: str) -> Rubric:
    if not _ID.fullmatch(rubric_id):
        raise RubricError(f"rubric id must be lower_snake_case, got {rubric_id!r}")
    source = resources.files("boss") / "rubrics" / f"{rubric_id}.json"
    if not source.is_file():
        raise RubricError(f"no rubric {rubric_id!r}")
    try:
        raw = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RubricError(f"{rubric_id}: not UTF-8 text") from exc
    return parse_rubric(rubric_id, raw)


def parse_rubric(rubric_id: str, raw: str) -> Rubric:
    def fail(message: str) -> RubricError:
        return RubricError(f"{rubric_id}: {message}")

    try:
        data = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (ValueError, RecursionError) as exc:
        raise fail(f"not valid JSON ({exc})") from exc
    if not isinstance(data, dict) or set(data) != {"id", "version", "title", "criteria"}:
        raise fail("must be an object with exactly id, version, title, criteria")
    if data["id"] != rubric_id:
        raise fail(f"id {data['id']!r} is not the file's name")
    version = data["version"]
    if type(version) is not int or version < 1:
        raise fail("version must be a whole number of 1 or more")
    if not _is_line(data["title"]):
        raise fail("title must be one line of text")
    raw_criteria = data["criteria"]
    if not isinstance(raw_criteria, list) or not MIN_CRITERIA <= len(raw_criteria) <= MAX_CRITERIA:
        raise fail(f"needs {MIN_CRITERIA} to {MAX_CRITERIA} criteria")
    criteria: list[Criterion] = []
    for item in raw_criteria:
        if not isinstance(item, dict) or set(item) != {"id", "question", "anchors"}:
            raise fail("each criterion must have exactly id, question, anchors")
        name = item["id"]
        if not isinstance(name, str) or not _ID.fullmatch(name):
            raise fail(f"criterion id must be lower_snake_case, got {name!r}")
        if name in {c.id for c in criteria}:
            raise fail(f"criterion {name!r} appears twice")
        if not _is_line(item["question"]):
            raise fail(f"{name}: question must be one line of text")
        anchors = item["anchors"]
        if not isinstance(anchors, dict) or set(anchors) != set(ANCHOR_POINTS):
            raise fail(f"{name}: anchors must be exactly {', '.join(ANCHOR_POINTS)}")
        if not all(isinstance(a, str) and a.strip() for a in anchors.values()):
            raise fail(f"{name}: every anchor needs text")
        criteria.append(
            Criterion(name, item["question"], tuple(anchors[p] for p in ANCHOR_POINTS))  # type: ignore[arg-type]
        )
    return Rubric(rubric_id, version, data["title"], tuple(criteria))


def all_rubric_ids() -> list[str]:
    """Every rubric file shipped, as ids, sorted."""
    root = resources.files("boss") / "rubrics"
    return sorted(p.name.removesuffix(".json") for p in root.iterdir() if p.name.endswith(".json"))


@dataclass(frozen=True, slots=True)
class Score:
    criterion: str
    score: int
    evidence: str  # a fragment of the artifact, as the model wrote it


@dataclass(frozen=True, slots=True)
class Judgement:
    rubric_id: str
    rubric_version: int
    model: str
    prompt: str  # the prompt file, e.g. judge_v1.md
    scores: tuple[Score, ...]  # in the rubric's order
    summary: str
    calibrated: bool = False  # only `judge_artifact` sets it; read it through `require_calibrated`

    @property
    def mean(self) -> float:
        return sum(s.score for s in self.scores) / len(self.scores)


class UncalibratedJudgeError(RuntimeError):
    """Code tried to act on a judgement that no calibration covers."""


def require_calibrated(judgement: Judgement) -> Judgement:
    """Return the judgement, or raise. Every code path that acts on a score calls this first."""
    if not judgement.calibrated:
        raise UncalibratedJudgeError(
            f"the {judgement.rubric_id} v{judgement.rubric_version} judgement by "
            f"{judgement.model} is uncalibrated: its scores are advisory, and nothing may act "
            "on them until a calibration that meets the bar covers this rubric version, model, "
            "prompt and skills"
        )
    return judgement


def judge_prompt(rubric: Rubric, artifact: str, context: str) -> str:
    """The user message: the rubric, then the context, then the artifact."""
    lines = [f"Rubric {rubric.id} (version {rubric.version}): {rubric.title}", ""]
    for criterion in rubric.criteria:
        lines.append(f"Criterion {criterion.id}: {criterion.question}")
        lines += [
            f"  {point}: {text}"
            for point, text in zip(ANCHOR_POINTS, criterion.anchors, strict=True)
        ]
    return "\n".join(
        [
            *lines,
            "",
            f"<context>\n{context}\n</context>",
            "",
            f"<artifact>\n{artifact}\n</artifact>",
        ]
    )


def verdict_problems(rubric: Rubric, artifact: str, data: object) -> list[str]:
    """Everything wrong with a model's output, as one line each. Empty means it passes the gate."""
    if not isinstance(data, Mapping):
        return ["output is not an object"]
    problems: list[str] = []
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("summary is missing or empty")
    scores = data.get("scores")
    if not isinstance(scores, list):
        return [*problems, "scores is not a list"]
    wanted = {c.id for c in rubric.criteria}
    scored: set[str] = set()
    haystack = normalise(artifact)
    for n, item in enumerate(scores, start=1):
        if not isinstance(item, Mapping):
            problems.append(f"score {n} is not an object")
            continue
        name = item.get("criterion")
        label = f"score {n}"
        if not isinstance(name, str) or name not in wanted:
            problems.append(f"{label}: not a criterion of {rubric.id}: {_show(name)}")
        elif name in scored:
            problems.append(f"{name}: scored more than once")
        else:
            scored.add(name)
            label = name
        value = item.get("score")
        if type(value) is not int or not MIN_SCORE <= value <= MAX_SCORE:
            problems.append(f"{label}: score must be an integer from 1 to 5, got {_show(value)}")
        evidence = item.get("evidence")
        if not isinstance(evidence, str) or len(normalise(evidence)) < MIN_EVIDENCE_CHARS:
            problems.append(
                f"{label}: evidence must quote at least {MIN_EVIDENCE_CHARS} characters"
            )
        elif normalise(evidence) not in haystack:
            problems.append(
                f"{label}: evidence is not a fragment of the artifact: {_show(evidence)}"
            )
    if wanted - scored:
        problems.append("criteria not scored: " + ", ".join(sorted(wanted - scored)))
    return problems


def judge_artifact(
    rubric: Rubric,
    artifact: str,
    context: str,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> tuple[Judgement, Usage]:
    """One call. Raises RoleError when the call fails and RoleOutputError when its output fails
    the gate; either way the caller books the spend from the error's `usage`."""
    if not artifact.strip() or not context.strip():
        raise ValueError("the artifact and the context it is judged against must both be text")
    if not model or model.startswith("-"):
        raise ValueError(f"model must be a model name, got {model!r}")
    out = call_role(
        JUDGE,
        judge_prompt(rubric, artifact, context),
        JUDGE_SCHEMA,
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
        timeout_s=timeout_s,
    )
    problems = verdict_problems(rubric, artifact, out.data)
    if problems:
        raise RoleOutputError(JUDGE.name, problems, out.usage)
    by_name = {item["criterion"]: item for item in out.data["scores"]}
    scores = tuple(
        Score(c.id, by_name[c.id]["score"], by_name[c.id]["evidence"]) for c in rubric.criteria
    )
    judgement = Judgement(
        rubric.id, rubric.version, model, JUDGE.prompt, scores, out.data["summary"].strip()
    )
    return judgement, out.usage


def render_judgement(judgement: Judgement) -> str:
    """The judgement as text for a person. Model text is made safe to show; the calibration
    status is always in the first line, in words."""
    status = (
        "calibrated" if judgement.calibrated else "uncalibrated: advisory only, do not act on it"
    )
    lines = [
        f"{judgement.rubric_id} v{judgement.rubric_version} by {_flat(judgement.model, 60)}: "
        f"mean {judgement.mean:.1f} of {MAX_SCORE} ({status})"
    ]
    for s in judgement.scores:
        lines.append(f'  {s.criterion}: {s.score}  "{_flat(s.evidence, _SHOWN_CHARS)}"')
    lines.append(f"  summary: {_flat(judgement.summary, 300)}")
    return "\n".join(lines)


def _is_line(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\n" not in value


def _flat(text: str, limit: int) -> str:
    return " ".join(safe_text(text, limit=limit).split())


def _show(value: object) -> str:
    return safe_text(repr(value), limit=60)
