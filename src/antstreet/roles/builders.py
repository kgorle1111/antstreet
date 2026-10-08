"""Worker profiles: which skills a builder's system prompt carries.

A profile is not a new kind of agent. It is the same worker, with the same tools (Read, Write and
Edit in its own folder, no shell), the same base prompt and the same gate, plus a different list
of skills appended to that prompt. Choosing a profile changes what the worker is told, nothing
it is allowed to do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from antstreet.boss import load_prompt
from antstreet.skills import load_skill

DEFAULT_PROFILE = "generalist"
DEFAULT_BASE_PROMPT = "builder_v5.md"  # pinned to firm.BUILDER_PROMPT by a test, not imported
_NAME = re.compile(r"[a-z][a-z_]{1,30}")

_EVERY_BUILDER = (
    "builder/request-first",
    "builder/exact-names",
    "builder/stated-edges",
    "builder/trace-by-hand",
    "builder/dispute-wrong-checks",
    "builder/honest-status",
)


@dataclass(frozen=True, slots=True)
class WorkerProfile:
    name: str  # lower_snake_case; also the folder that holds its own skills
    purpose: str  # one line: what this builder is for
    skills: tuple[str, ...]  # skill ids appended to the base prompt, in order
    suited_to: str  # one line: the work it fits, and what has not measured it

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ValueError(f"profile name must be lower_snake_case, got {self.name!r}")
        if not self.purpose.strip() or not self.suited_to.strip():
            raise ValueError(f"profile {self.name} needs a purpose and a suited_to")
        if len(set(self.skills)) != len(self.skills):
            raise ValueError(f"profile {self.name} lists a skill twice: every skill is paid for")


PROFILES: tuple[WorkerProfile, ...] = (
    WorkerProfile(
        "generalist",
        "The default builder: the base prompt and the skills every builder needs.",
        _EVERY_BUILDER,
        "Any product built from a written request; the profile the benchmark tasks would use.",
    ),
    WorkerProfile(
        "backend_engineer",
        "Data structures, parsing, state and error handling at the edges of a module.",
        (*_EVERY_BUILDER, "backend_engineer/validate-first", "backend_engineer/bounded-work"),
        "Parsers, matchers, evaluators and state holders with stated errors and size limits.",
    ),
    WorkerProfile(
        "ai_engineer",
        "Code that calls or evaluates a model: guards around one call, and an eval first.",
        (
            *_EVERY_BUILDER,
            "ai_engineer/guard-model-output",
            "ai_engineer/eval-before-prompt-change",
        ),
        "Structured-output pipelines and prompt evals. Not exercised by the benchmark yet: its "
        "products are standard-library only, so no task calls a model.",
    ),
    WorkerProfile(
        "test_engineer",
        "Test suites and fixtures as the product, with expected values taken from the request.",
        (*_EVERY_BUILDER, "test_engineer/tests-that-can-fail"),
        "Tasks whose deliverable is a pytest suite for a module the request describes.",
    ),
    WorkerProfile(
        "refactorer",
        "Changes existing code without changing behaviour, in the smallest diff.",
        (*_EVERY_BUILDER, "refactorer/preserve-behaviour"),
        "Renames, extractions and cleanups in a folder that already holds working code.",
    ),
)


def profile(name: str) -> WorkerProfile:
    for candidate in PROFILES:
        if candidate.name == name:
            return candidate
    known = ", ".join(p.name for p in PROFILES)
    raise ValueError(f"unknown worker profile {name!r}; known profiles: {known}")


def builder_system_prompt(profile_name: str, base_prompt_name: str = DEFAULT_BASE_PROMPT) -> str:
    """The base prompt, then each of the profile's skills in order.

    The base prompt comes back unchanged, byte for byte, when the profile has no skills, and it
    is always the exact prefix of the result: the live loop can switch to this function without
    changing what a worker is told unless a profile says so.
    """
    base = load_prompt(base_prompt_name)
    texts = [load_skill(skill).text for skill in profile(profile_name).skills]
    if not texts:
        return base
    gap = "\n" if base.endswith("\n") else "\n\n"
    return base + gap + "\n\n".join(texts) + "\n"
