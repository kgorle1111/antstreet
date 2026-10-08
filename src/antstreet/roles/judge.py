"""The judge: scores an artifact that cannot be checked by running it, against a rubric, and
quotes the evidence for every score.

A judgement is ADVISORY. It is labelled `uncalibrated` until a calibration file shows the same
judge (rubric id and version, model, prompt and skills) agreeing with a person on enough cases,
and nothing in the firm may gate on an uncalibrated judgement. Any code path that acts on a score
must call `require_calibrated` first; `Judgement.calibrated` is set by `judge_artifact` alone.

Calibration is a person scoring about twenty artifacts by hand, `calibrate` running the judge on
the same artifacts, and the two sets of scores compared (`meets_bar`). Commands:

    python -m antstreet.roles.judge template --rubric ID --artifacts DIR --out FILE
    python -m antstreet.roles.judge calibrate --cases FILE --out FILE [--model M] [--dry-run]
    python -m antstreet.roles.judge show FILE

The judge drafts a score; the gate below is pure code: every criterion scored once, integer
scores from 1 to 5, and every piece of evidence a fragment of the artifact. Grounding beats
begging: a score with no quote from the artifact is not accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from antstreet.boss import DEFAULT_MODEL
from antstreet.redact import safe_text
from antstreet.roles.base import RoleError, RoleOutputError, RoleSpec, call_role
from antstreet.roles.stories import normalise
from antstreet.skills import load_skill
from antstreet.stats import md_table, rate
from antstreet.stream import Usage
from antstreet.worker import CLI, EXECUTABLE_VAR, billing_mode, usd, worker_env

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
    source = resources.files("antstreet") / "rubrics" / f"{rubric_id}.json"
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
        criteria.append(Criterion(name, item["question"], tuple(anchors[p] for p in ANCHOR_POINTS)))
    return Rubric(rubric_id, version, data["title"], tuple(criteria))


def all_rubric_ids() -> list[str]:
    """Every rubric file shipped, as ids, sorted."""
    root = resources.files("antstreet") / "rubrics"
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
    calibration: Calibration | None = None,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> tuple[Judgement, Usage]:
    """One call. Raises RoleError when the call fails and RoleOutputError when its output fails
    the gate; either way the caller books the spend from the error's `usage`. The judgement is
    calibrated only if `calibration` applies to this rubric, model, prompt and skills and meets
    the bar."""
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
        raise RoleOutputError(JUDGE.name, problems, out.usage, out.data)
    by_name = {item["criterion"]: item for item in out.data["scores"]}
    scores = tuple(
        Score(c.id, by_name[c.id]["score"], by_name[c.id]["evidence"]) for c in rubric.criteria
    )
    calibrated = (
        calibration is not None
        and applies_to(calibration, rubric, model)
        and meets_bar(calibration)
    )
    judgement = Judgement(
        rubric.id, rubric.version, model, JUDGE.prompt, scores, out.data["summary"].strip(),
        calibrated,
    )  # fmt: skip
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


# --- calibration -----------------------------------------------------------------------------

# A starting point, to be revised against evidence: these are not a claim about the right values.
MIN_CASES = 20  # scored cases (failed ones do not count); the owner's standing rule
MIN_WEIGHTED_KAPPA = 0.6  # quadratic-weighted kappa, overall
MIN_WITHIN_ONE = 0.8  # share of all score pairs within one point; failed calls count against it
CALIBRATION_FORMAT = 1
CALIBRATION_CAVEAT = (
    "Score pairs from one case are not independent, so the intervals are narrower than they "
    "should be; per-criterion rows are descriptive. A calibration covers only the rubric "
    "version, model, prompt and skills named above."
)
_CASE_KEYS = {"id", "rubric", "artifact", "context", "scores"}
_CALIBRATION_KEYS = {
    "format", "rubric_id", "rubric_version", "model", "prompt", "skills", "cases_sha",
    "cases", "failed", "overall", "per_criterion", "results",
}  # fmt: skip


class CaseFileError(ValueError):
    """A case file is missing or malformed. The message names the line."""


class CalibrationError(ValueError):
    """A calibration file is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    rubric: str  # rubric id
    artifact: str
    context: str  # what the artifact is judged against, for example the idea
    scores: dict[str, int]  # the person's score per criterion, in the rubric's order


def write_template(rubric: Rubric, artifacts: Path, out: Path) -> int:
    """Write an UNLABELLED case file with one case per file in `artifacts`, so the person only
    fills in each context and each score. Never overwrites: a labelled file is hours of work."""
    files = sorted(p for p in artifacts.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        raise CaseFileError(f"no artifact files in {artifacts}")
    lines = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise CaseFileError(f"{path.name} is not UTF-8 text") from None
        if not text.strip():
            raise CaseFileError(f"{path.name} is empty")
        blank = {c.id: None for c in rubric.criteria}
        case = {
            "id": path.name,
            "rubric": rubric.id,
            "artifact": text,
            "context": "",
            "scores": blank,
        }
        lines.append(json.dumps(case, ensure_ascii=False))
    try:
        with out.open("x", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except FileExistsError:
        raise CaseFileError(f"{out} exists; not overwriting it, choose another path") from None
    return len(lines)


def load_cases(path: Path) -> tuple[list[Case], str]:
    """The validated cases of a labelled file and the SHA-256 of the file's bytes."""
    try:
        raw = path.read_bytes()
        return parse_cases(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise CaseFileError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError:
        raise CaseFileError(f"{path} is not UTF-8 text") from None
    except CaseFileError as exc:
        raise CaseFileError(f"{path}: {exc}") from exc


def parse_cases(text: str) -> list[Case]:
    """JSON Lines, one case per line, blank lines ignored. Every error names its line."""
    cases: list[Case] = []
    seen: dict[str, int] = {}  # case id -> the line it first appeared on
    rubric: Rubric | None = None
    for n, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line, object_pairs_hook=reject_duplicate_keys)
        except (ValueError, RecursionError) as exc:
            raise _bad(n, f"not valid JSON ({exc})") from exc
        if not isinstance(raw, dict) or set(raw) != _CASE_KEYS:
            raise _bad(n, f"must be an object with exactly {', '.join(sorted(_CASE_KEYS))}")
        rubric = _rubric_of(n, raw["rubric"], rubric)
        case_id = raw["id"]
        if not isinstance(case_id, str) or not case_id or case_id != case_id.strip():
            raise _bad(n, "id must be non-empty text without surrounding spaces")
        if case_id in seen:
            raise _bad(n, f"id {case_id!r} is already used on line {seen[case_id]}")
        seen[case_id] = n
        for key in ("artifact", "context"):
            if not isinstance(raw[key], str) or not raw[key].strip():
                hint = "; say what it is judged against, e.g. the idea" if key == "context" else ""
                raise _bad(n, f"{key} is empty{hint}")
        scores = _human(n, rubric, raw["scores"])
        cases.append(Case(case_id, rubric.id, raw["artifact"], raw["context"], scores))
    if not cases:
        raise CaseFileError("no cases")
    return cases


def _rubric_of(n: int, name: object, current: Rubric | None) -> Rubric:
    if not isinstance(name, str):
        raise _bad(n, "rubric must be a rubric id")
    if current is not None:
        if name != current.id:
            raise _bad(n, f"rubric {name!r} differs from {current.id!r}; one file, one rubric")
        return current
    try:
        return load_rubric(name)
    except RubricError as exc:
        raise _bad(n, str(exc)) from exc


def _human(n: int, rubric: Rubric, scores: object) -> dict[str, int]:
    if not isinstance(scores, dict):
        raise _bad(n, "scores must be an object with one entry per criterion")
    unknown = sorted(set(scores) - {c.id for c in rubric.criteria})
    if unknown:
        raise _bad(n, f"not criteria of {rubric.id}: {', '.join(map(_show, unknown))}")
    out: dict[str, int] = {}
    for criterion in rubric.criteria:
        value = scores.get(criterion.id)
        if value is None:
            raise _bad(n, f"criterion {criterion.id!r} is not scored yet (needs 1 to 5)")
        if type(value) is not int or not MIN_SCORE <= value <= MAX_SCORE:
            raise _bad(n, f"{criterion.id!r}: must be an integer from 1 to 5, got {_show(value)}")
        out[criterion.id] = value
    return out


def _bad(n: int, message: str) -> CaseFileError:
    return CaseFileError(f"line {n}: {message}")


def weighted_kappa(pairs: Sequence[tuple[int, int]]) -> float | None:
    """Cohen's kappa with quadratic weights for (person, judge) score pairs on an ordinal scale:
    1 - observed / expected, where both are mean squared score differences, observed over the
    pairs and expected over every person-score by judge-score combination (the two raters'
    marginals taken as independent). 1 is perfect agreement, 0 is chance, below 0 is worse.

    None when either rater used one score throughout: kappa then cannot show whether the judge
    tells good artifacts from bad ones. (The formula gives 0/0 when both used the same single
    score and exactly 0 when only one did; None keeps both out of `meets_bar` alike.)
    """
    person, judge = Counter(p for p, _ in pairs), Counter(j for _, j in pairs)
    if len(person) < 2 or len(judge) < 2:
        return None
    n = len(pairs)
    observed = sum((p - j) ** 2 for p, j in pairs) / n
    expected = sum(pc * jc * (p - j) ** 2 for p, pc in person.items() for j, jc in judge.items())
    return 1 - observed / (expected / n**2)


@dataclass(frozen=True, slots=True)
class Figures:
    """How the judge compares with the person over a set of score pairs."""

    pairs: int  # every pair the person's scores call for: cases x criteria
    compared: int  # of those, the pairs the judge actually scored
    exact: int  # pairs with equal scores
    within_one: int  # pairs at most one point apart (includes exact)
    mean_diff: float | None  # mean of judge minus person over compared; > 0: judge scores higher
    kappa: float | None  # weighted_kappa over compared

    @property
    def exact_rate(self) -> float:
        return self.exact / self.pairs

    @property
    def within_one_rate(self) -> float:
        return self.within_one / self.pairs

    def to_data(self) -> dict[str, Any]:
        return {
            "pairs": self.pairs,
            "compared": self.compared,
            "exact": self.exact,
            "within_one": self.within_one,
            "mean_diff": self.mean_diff,
            "kappa": self.kappa,
        }


def figures_of(pairs: Sequence[tuple[int, int | None]]) -> Figures:
    """Figures for (person, judge) pairs; judge None is a call that failed or failed the gate.
    Such a pair is a disagreement in the rates and absent from the mean and kappa: it is never
    dropped and never counted as agreement."""
    got = [(p, j) for p, j in pairs if j is not None]
    return Figures(
        pairs=len(pairs),
        compared=len(got),
        exact=sum(p == j for p, j in got),
        within_one=sum(abs(p - j) <= 1 for p, j in got),
        mean_diff=sum(j - p for p, j in got) / len(got) if got else None,
        kappa=weighted_kappa(got),
    )


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: str
    human: dict[str, int]
    judge: dict[str, int] | None  # None: the call failed or its output failed the gate
    failure: str = ""  # why, when judge is None


@dataclass(frozen=True, slots=True)
class Calibration:
    """The judge's record against a person: which judge it covers, and the per-case scores its
    figures are computed from, so a saved file cannot disagree with itself."""

    rubric_id: str
    rubric_version: int
    model: str
    prompt: str
    skills: tuple[str, ...]  # "<skill id>@<version>"
    cases_sha: str  # SHA-256 of the labelled cases file
    results: tuple[CaseResult, ...]

    @property
    def cases(self) -> int:
        return len(self.results)

    @property
    def failed(self) -> int:
        return sum(r.judge is None for r in self.results)

    @property
    def criteria(self) -> tuple[str, ...]:
        return tuple(self.results[0].human)

    @property
    def overall(self) -> Figures:
        return figures_of(self._pairs(self.criteria))

    @property
    def per_criterion(self) -> dict[str, Figures]:
        return {c: figures_of(self._pairs((c,))) for c in self.criteria}

    def _pairs(self, criteria: Sequence[str]) -> list[tuple[int, int | None]]:
        return [
            (r.human[c], None if r.judge is None else r.judge[c])
            for r in self.results
            for c in criteria
        ]

    def to_data(self) -> dict[str, Any]:
        return {
            "format": CALIBRATION_FORMAT,
            "rubric_id": self.rubric_id,
            "rubric_version": self.rubric_version,
            "model": self.model,
            "prompt": self.prompt,
            "skills": list(self.skills),
            "cases_sha": self.cases_sha,
            "cases": self.cases,
            "failed": self.failed,
            "overall": self.overall.to_data(),
            "per_criterion": {c: f.to_data() for c, f in self.per_criterion.items()},
            "results": [
                {"case": r.case, "human": r.human, "judge": r.judge, "failure": r.failure}
                for r in self.results
            ],
        }

    def save(self, path: Path) -> None:
        """Write the calibration; raises FileExistsError rather than replace an earlier one."""
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(self.to_data(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: Path) -> Calibration:
        try:
            data = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
            )
        except OSError as exc:
            raise CalibrationError(f"cannot read {path}: {exc.strerror or exc}") from exc
        except (ValueError, RecursionError) as exc:
            raise CalibrationError(f"{path}: not valid JSON ({exc})") from exc
        try:
            return cls.from_data(data)
        except CalibrationError as exc:
            raise CalibrationError(f"{path}: {exc}") from exc

    @classmethod
    def from_data(cls, data: object) -> Calibration:
        """Rebuild from `to_data`'s shape. The recorded figures must equal the figures recomputed
        from the recorded scores: a hand-edited number is an error, not a calibration."""
        if (
            not isinstance(data, dict)
            or set(data) != _CALIBRATION_KEYS
            or data["format"] != CALIBRATION_FORMAT
        ):
            raise CalibrationError(f"must be a format {CALIBRATION_FORMAT} calibration object")
        text_fields = ("rubric_id", "model", "prompt", "cases_sha")
        if not all(isinstance(data[k], str) and data[k] for k in text_fields):
            raise CalibrationError(f"{', '.join(text_fields)} must be text")
        if type(data["rubric_version"]) is not int or data["rubric_version"] < 1:
            raise CalibrationError("rubric_version must be a whole number of 1 or more")
        skills = data["skills"]
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            raise CalibrationError("skills must be a list of text")
        raw_results = data["results"]
        if not isinstance(raw_results, list) or not raw_results:
            raise CalibrationError("results must be a non-empty list")
        results = tuple(_result(item) for item in raw_results)
        criteria = set(results[0].human)
        if len({r.case for r in results}) != len(results):
            raise CalibrationError("a case appears twice in results")
        if any(set(r.human) != criteria or (r.judge and set(r.judge) != criteria) for r in results):
            raise CalibrationError("every result must score the same criteria")
        loaded = cls(
            data["rubric_id"], data["rubric_version"], data["model"], data["prompt"],
            tuple(skills), data["cases_sha"], results,
        )  # fmt: skip
        fresh = loaded.to_data()
        if any(data[k] != fresh[k] for k in ("cases", "failed", "overall", "per_criterion")):
            raise CalibrationError("the recorded figures do not match the recorded scores")
        return loaded


def _result(item: object) -> CaseResult:
    if not isinstance(item, dict) or set(item) != {"case", "human", "judge", "failure"}:
        raise CalibrationError("each result must have exactly case, human, judge, failure")
    if not isinstance(item["case"], str) or not isinstance(item["failure"], str):
        raise CalibrationError("a result's case and failure must be text")
    judge = None if item["judge"] is None else _scores(item["judge"])
    if (judge is None) != bool(item["failure"]):
        raise CalibrationError("a result has a failure reason exactly when the judge has no scores")
    return CaseResult(item["case"], _scores(item["human"]), judge, item["failure"])


def _scores(value: object) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise CalibrationError("scores must be a non-empty object")
    for name, score in value.items():
        if type(score) is not int or not MIN_SCORE <= score <= MAX_SCORE:
            raise CalibrationError(f"{name}: score must be an integer from 1 to 5")
    return value


def judge_identity() -> tuple[str, tuple[str, ...]]:
    """What a calibration must have been run against: the prompt file and each skill's version."""
    return JUDGE.prompt, tuple(f"{s}@{load_skill(s).version}" for s in JUDGE.skills)


def applies_to(calibration: Calibration, rubric: Rubric, model: str) -> bool:
    """A calibration covers one judge: this rubric id and version, this model, and the prompt
    file and skill versions the judge runs with now. Any other calibration does not count."""
    prompt, skills = judge_identity()
    return (
        calibration.rubric_id == rubric.id
        and calibration.rubric_version == rubric.version
        and calibration.model == model
        and calibration.prompt == prompt
        and calibration.skills == skills
    )


def bar_shortfalls(
    calibration: Calibration,
    *,
    min_cases: int = MIN_CASES,
    min_weighted_kappa: float = MIN_WEIGHTED_KAPPA,
    min_within_one: float = MIN_WITHIN_ONE,
) -> list[str]:
    """Why a calibration does not meet the bar, one line each; empty means it does. The bar is
    judged on the overall figures, and every bound is inclusive."""
    overall = calibration.overall
    problems = []
    scored = calibration.cases - calibration.failed
    if scored < min_cases:
        problems.append(f"{scored} scored cases, needs {min_cases}")
    if overall.kappa is None:
        problems.append("weighted kappa is undefined: a rater used one score throughout")
    elif overall.kappa < min_weighted_kappa:
        problems.append(f"weighted kappa {overall.kappa:.2f}, needs {min_weighted_kappa:.2f}")
    if overall.within_one_rate < min_within_one:
        problems.append(
            f"within one point {overall.within_one_rate:.0%}, needs {min_within_one:.0%}"
        )
    return problems


def meets_bar(
    calibration: Calibration,
    *,
    min_cases: int = MIN_CASES,
    min_weighted_kappa: float = MIN_WEIGHTED_KAPPA,
    min_within_one: float = MIN_WITHIN_ONE,
) -> bool:
    return not bar_shortfalls(
        calibration,
        min_cases=min_cases,
        min_weighted_kappa=min_weighted_kappa,
        min_within_one=min_within_one,
    )


JudgeFn = Callable[[Case], Judgement]


def calibrate(
    cases: Sequence[Case], judge_fn: JudgeFn, *, rubric: Rubric, model: str, cases_sha: str
) -> Calibration:
    """Run the judge on every case and compare with the person's scores. `judge_fn` is injected;
    a RoleError from it (call failed, or output failed the gate) is recorded against the case,
    not raised, so a judge that fails is measured as failing rather than skipped."""
    if not cases:
        raise ValueError("cannot calibrate on no cases")
    results = []
    for case in cases:
        if case.rubric != rubric.id:
            raise ValueError(f"case {case.id!r} is for rubric {case.rubric!r}, not {rubric.id!r}")
        human = dict(case.scores)
        try:
            judged = {s.criterion: s.score for s in judge_fn(case).scores}
        except RoleError as exc:
            results.append(CaseResult(case.id, human, None, _flat(str(exc), 200) or "failed"))
            continue
        if set(judged) != set(human):
            results.append(CaseResult(case.id, human, None, "the judge scored other criteria"))
        else:
            results.append(CaseResult(case.id, human, judged))
    prompt, skills = judge_identity()
    return Calibration(rubric.id, rubric.version, model, prompt, skills, cases_sha, tuple(results))


def render_calibration(calibration: Calibration) -> str:
    """The calibration as text: figures with 95% Wilson intervals, the bar, and the failures."""
    cal, overall = calibration, calibration.overall
    lines = [
        f"Calibration of {cal.rubric_id} v{cal.rubric_version} with model {_flat(cal.model, 60)}",
        f"prompt {cal.prompt}; skills {', '.join(cal.skills)}; "
        f"cases file sha256 {cal.cases_sha[:12]}",
        f"cases {cal.cases}, of which {cal.failed} failed: a failed case counts against agreement "
        "and is never dropped",
        "",
    ]
    rows = [_row("overall", overall)] + [
        _row(c + ("" if not _below_bar(f) else " (below bar)"), f)
        for c, f in cal.per_criterion.items()
    ]
    header = [
        "criterion",
        "pairs",
        "exact [95% CI]",
        "within one [95% CI]",
        "judge - person",
        "kappa",
    ]
    lines += md_table(header, rows)
    problems = bar_shortfalls(cal)
    lines += [
        "",
        f"Bar, a starting point and not a claim about the right values: at least {MIN_CASES} "
        f"scored cases, weighted kappa >= {MIN_WEIGHTED_KAPPA}, within one point >= "
        f"{MIN_WITHIN_ONE:.0%}, on the overall row.",
        "Meets the bar." if not problems else "Does not meet the bar: " + "; ".join(problems) + ".",
    ]
    failures = [r for r in cal.results if r.judge is None]
    if failures:
        lines += ["", "Failed cases:"]
        lines += [f"- {_flat(r.case, 80)}: {_flat(r.failure, 200)}" for r in failures]
    return "\n".join([*lines, "", CALIBRATION_CAVEAT]) + "\n"


def _below_bar(figures: Figures) -> bool:
    kappa = figures.kappa
    return kappa is None or kappa < MIN_WEIGHTED_KAPPA or figures.within_one_rate < MIN_WITHIN_ONE


def _row(name: str, f: Figures) -> list[str]:
    return [
        name,
        f"{f.compared}/{f.pairs}",
        rate(f.exact, f.pairs),
        rate(f.within_one, f.pairs),
        "n/a" if f.mean_diff is None else f"{f.mean_diff:+.2f}",
        "undefined" if f.kappa is None else f"{f.kappa:.2f}",
    ]


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m antstreet.roles.judge", description="Calibrate the judge against a person."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="write an unlabelled case file")
    template.add_argument("--rubric", required=True)
    template.add_argument("--artifacts", type=Path, required=True, help="a folder of text files")
    template.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("calibrate", help="run the judge on a labelled case file")
    run.add_argument("--cases", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--dry-run", action="store_true", help="show the calls and their cost ceiling")
    show = commands.add_parser("show", help="print a calibration file")
    show.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        if args.command == "template":
            count = write_template(load_rubric(args.rubric), args.artifacts, args.out)
            print(f"wrote {count} unlabelled cases to {args.out}")
            print("fill in every context and every score (1 to 5), then run `calibrate`")
        elif args.command == "show":
            print(render_calibration(Calibration.load(args.file)), end="")
        else:
            return _calibrate(args, environ)
    except (CaseFileError, RubricError, CalibrationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _calibrate(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    cases, sha = load_cases(args.cases)
    rubric = load_rubric(cases[0].rubric)
    if args.out.exists() or not args.out.parent.is_dir():
        raise CalibrationError(f"cannot write {args.out}: it exists or its folder does not")
    env = worker_env(environ)
    print(
        f"{len(cases)} calls to model {args.model} ({billing_mode(env)} billing), at most "
        f"${usd(len(cases) * JUDGE.cap_micros)} in all ({JUDGE.name} cap: ${usd(JUDGE.cap_micros)} "
        "a call); rubric "
        f"{rubric.id} v{rubric.version}"
    )
    if args.dry_run:
        print("dry run: no calls made")
        for case in cases:
            print(f"  {case.id}")
        return 0
    spent: list[Usage] = []

    def judge_fn(case: Case) -> Judgement:
        try:
            judged, usage = judge_artifact(
                rubric,
                case.artifact,
                case.context,
                env=env,
                model=args.model,
                executable=environ.get(EXECUTABLE_VAR, CLI),
            )
        except RoleError as exc:
            spent.append(exc.usage)
            print(f"  {_flat(case.id, 60)}: failed, {_flat(str(exc), 120)}")
            raise
        spent.append(usage)
        print(f"  {_flat(case.id, 60)}: mean {judged.mean:.1f}")
        return judged

    calibration = calibrate(cases, judge_fn, rubric=rubric, model=args.model, cases_sha=sha)
    known = sum(u.cost_micros for u in spent if u.cost_micros is not None)
    unknown = sum(u.cost_micros is None for u in spent)
    print(
        f"spent ${usd(known)} by the CLI's estimate"
        + (f", plus {unknown} calls of unknown cost" if unknown else "")
    )
    calibration.save(args.out)
    print(f"wrote {args.out}\n")
    print(render_calibration(calibration), end="")
    return 0


def _is_line(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\n" not in value


def _flat(text: str, limit: int) -> str:
    return " ".join(safe_text(text, limit=limit).split())


def _show(value: object) -> str:
    return safe_text(repr(value), limit=60)


if __name__ == "__main__":
    sys.exit(main())
