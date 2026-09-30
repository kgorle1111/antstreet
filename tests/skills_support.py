"""The quality bar for skills, as functions over skills. Not a test module: the tests in
`test_skills_quality.py` apply it to every shipped skill and to bad skills made for the purpose,
and `test_docs_roles.py` uses it to check the steps `docs/ROLES.md` gives."""

import re
from collections.abc import Mapping

from boss.roles import registry
from boss.roles.builders import PROFILES
from boss.skills import MAX_SKILL_CHARS, Skill, all_skill_ids, load_skill

# Filler that costs tokens and changes nothing: politeness, role-play, and exhortations no one can
# check. Matched as whole words or phrases, case-insensitively.
BANNED_PHRASES = (
    "please",
    "be accurate",
    "be careful",
    "you are an expert",
    "as an ai",
    "do your best",
)

# The most skill text one role or profile may carry. At about 4 characters a token this is 2,500
# tokens on every call, eight times the 1,252-character base builder prompt. The largest shipped
# set is about 8,400 characters: the cap leaves room for one more skill, not for two.
MAX_COMBINED_CHARS = 10_000


def skill_problems(skill: Skill) -> list[str]:
    problems = []
    if len(skill.text) > MAX_SKILL_CHARS:
        problems.append(f"{skill.id}: {len(skill.text)} characters, over {MAX_SKILL_CHARS}")
    for phrase in BANNED_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", skill.text, re.I):
            problems.append(f"{skill.id}: contains the filler phrase {phrase!r}")
    return problems


def duplicate_problems(skills: list[Skill]) -> list[str]:
    def norm(text: str) -> str:
        return " ".join(text.lower().split())

    problems = []
    for field in ("text", "description"):
        seen: dict[str, str] = {}
        for skill in skills:
            key = norm(getattr(skill, field))
            if key in seen:
                problems.append(f"{seen[key]} and {skill.id} have the same {field}")
            seen.setdefault(key, skill.id)
    return problems


def usage_problems(shipped: list[str], users: Mapping[str, tuple[str, ...]]) -> list[str]:
    """`users` maps each role or profile to the skills it names."""
    named = {skill for skills in users.values() for skill in skills}
    problems = [
        f"{s} is used by no role and no profile: delete it or use it"
        for s in shipped
        if s not in named
    ]
    for user, skills in sorted(users.items()):
        problems += [f"{user} names {s}, which is not shipped" for s in skills if s not in shipped]
    return problems


def combined_problems(users: Mapping[str, tuple[str, ...]], size: Mapping[str, int]) -> list[str]:
    """`size` maps each skill id to its body length."""
    problems = []
    for user, skills in sorted(users.items()):
        total = sum(size[s] for s in skills)
        if total > MAX_COMBINED_CHARS:
            problems.append(
                f"{user} carries {total} characters of skills, over {MAX_COMBINED_CHARS}"
            )
    return problems


def users() -> dict[str, tuple[str, ...]]:
    named = {f"role:{name}": spec.skills for name, spec in registry().items()}
    return named | {f"profile:{p.name}": p.skills for p in PROFILES}


def shipped() -> list[Skill]:
    return [load_skill(skill_id) for skill_id in all_skill_ids()]
