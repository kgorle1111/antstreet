"""Skills: versioned prompt modules a role's system prompt is built from.

A skill is a Markdown file `skills/<role>/<name>.md` with a small header. Workers and roles run
with the CLI's own skills and plugins switched off (safe mode), so these are plain text this
package appends to a system prompt, and they are code: versioned, reviewed and tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

MAX_SKILL_CHARS = 4_000  # every token of a skill is paid for on every call that loads it
_ID = re.compile(r"[a-z][a-z_]*/[a-z][a-z0-9-]*")
_HEADER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
_FIELDS = ("name", "version", "description")


class SkillError(ValueError):
    """A skill file is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Skill:
    id: str  # "<role>/<name>"
    version: int
    description: str
    text: str  # the body, appended to a system prompt


def load_skill(skill_id: str) -> Skill:
    if not _ID.fullmatch(skill_id):
        raise SkillError(f"skill id must look like role/name, got {skill_id!r}")
    role, name = skill_id.split("/")
    source = resources.files("antstreet") / "skills" / role / f"{name}.md"
    if not source.is_file():
        raise SkillError(f"no skill {skill_id!r}")
    return parse_skill(skill_id, source.read_text(encoding="utf-8"))


def parse_skill(skill_id: str, raw: str) -> Skill:
    match = _HEADER.match(raw)
    if not match:
        raise SkillError(f"{skill_id}: must start with a header between --- lines")
    header = dict(
        (key.strip(), value.strip())
        for key, _, value in (line.partition(":") for line in match[1].splitlines() if line.strip())
    )
    if set(header) != set(_FIELDS):
        raise SkillError(f"{skill_id}: header must have exactly {', '.join(_FIELDS)}")
    name = skill_id.split("/")[1]
    if header["name"] != name:
        raise SkillError(f"{skill_id}: header name {header['name']!r} is not the file's name")
    if not header["version"].isdecimal() or int(header["version"]) < 1:
        raise SkillError(f"{skill_id}: version must be a whole number of 1 or more")
    body = match[2].strip()
    if not header["description"] or not body:
        raise SkillError(f"{skill_id}: needs a description and a body")
    if len(body) > MAX_SKILL_CHARS:
        raise SkillError(f"{skill_id}: body is {len(body)} characters, over {MAX_SKILL_CHARS}")
    return Skill(skill_id, int(header["version"]), header["description"], body)


def all_skill_ids() -> list[str]:
    """Every skill file shipped, as ids, sorted."""
    root = resources.files("antstreet") / "skills"
    ids = []
    for role in sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != "__pycache__"):
        for file in sorted(p.name for p in (root / role).iterdir() if p.name.endswith(".md")):
            ids.append(f"{role}/{file.removesuffix('.md')}")
    return ids
