"""The organisation as it is defined, not as it is described: a chart built from each role's
`department` and `reports_to`, so the list of roles is never written down twice.

Investor, then the boss, then departments, then roles. A role that reports to another role hangs
under it. Worker profiles hang under engineering: they are builders, not roles, and are shown so
that the whole firm is on one page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boss.roles.base import DEPARTMENTS, RoleSpec
from boss.roles.builders import WorkerProfile

BOSS = "boss"
INVESTOR = "investor"
RESERVED = (BOSS, INVESTOR)
BUILDER_GATE = "the approved checks, run by the gate after every slice"


class OrgError(ValueError):
    """The roles do not form a tree under the boss."""


@dataclass(frozen=True, slots=True)
class OrgNode:
    name: str
    kind: str  # "investor", "boss", "department", "role" or "profile"
    purpose: str = ""
    gate: str = ""
    skills: tuple[str, ...] = ()
    suited_to: str = ""  # profiles only
    default_on: bool | None = None  # None where on/off has no meaning (people, departments)
    children: tuple[OrgNode, ...] = ()


def org_problems(registry: Mapping[str, RoleSpec]) -> list[str]:
    """Everything that stops the roles forming a tree under the boss. Empty means sound.
    A department with no role is not a problem."""
    problems: list[str] = []
    for name in sorted(registry):
        parent = registry[name].reports_to
        if name in RESERVED:
            problems.append(f"role {name} has a reserved name")
        if parent == name:
            problems.append(f"role {name} reports to itself")
        elif parent != BOSS and parent not in registry:
            problems.append(f"role {name} reports to {parent}, which is not a role")
    for cycle in sorted(_cycles(registry)):
        problems.append(f"roles {', '.join(cycle)} report to each other in a cycle")
    return problems


def _cycles(registry: Mapping[str, RoleSpec]) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    for start in registry:
        path: list[str] = []
        here = start
        while here in registry and here not in path:
            path.append(here)
            here = registry[here].reports_to
        if here in path and len(path) - path.index(here) > 1:  # a self-report is its own problem
            found.add(tuple(sorted(path[path.index(here) :])))
    return found


def org_chart(
    registry: Mapping[str, RoleSpec],
    profiles: Sequence[WorkerProfile],
    default_profile: str | None = None,
) -> OrgNode:
    """The tree of the firm. A broken org raises OrgError with every problem and is not drawn."""
    problems = org_problems(registry)
    if problems:
        raise OrgError("; ".join(problems))
    reports: dict[str, list[str]] = {}
    for name in sorted(registry):
        reports.setdefault(registry[name].reports_to, []).append(name)

    def role(name: str) -> OrgNode:  # recurses once per level of management, never per role
        spec = registry[name]
        return OrgNode(
            name,
            "role",
            spec.purpose,
            spec.gate,
            spec.skills,
            default_on=spec.default_on,
            children=tuple(role(sub) for sub in reports.get(name, ())),
        )

    departments = []
    for department in DEPARTMENTS:
        members = [role(n) for n in reports.get(BOSS, ()) if registry[n].department == department]
        if department == "engineering":
            members += [_profile_node(p, default_profile) for p in profiles]
        if members:
            departments.append(OrgNode(department, "department", children=tuple(members)))
    boss = OrgNode(
        BOSS,
        "boss",
        "drafts the tasks and the checks; the gate decides",
        children=tuple(departments),
    )
    return OrgNode(
        INVESTOR,
        "investor",
        "funds the idea, approves the checks, rules on disputes",
        children=(boss,),
    )


def _profile_node(profile: WorkerProfile, default_profile: str | None) -> OrgNode:
    return OrgNode(
        profile.name,
        "profile",
        profile.purpose,
        BUILDER_GATE,
        profile.skills,
        profile.suited_to,
        # A profile is on only if the loop uses it without being asked: none is, until one
        # is measured to earn its tokens.
        default_on=profile.name == default_profile,
    )


def render_org(root: OrgNode) -> str:
    """The chart as a plain-text tree: for each role or profile its purpose, gate, skills and
    whether it is on by default."""
    lines: list[str] = []

    def draw(node: OrgNode, prefix: str, last: bool, top: bool) -> None:
        head = node.name
        if node.kind in ("role", "profile"):
            head += f"  [{node.kind}, {'on' if node.default_on else 'off'} by default]"
        if node.purpose:
            head += f"  {node.purpose}"
        lines.append(head if top else f"{prefix}{'`-- ' if last else '|-- '}{head}")
        below = "" if top else prefix + ("    " if last else "|   ")
        detail = below + ("|  " if node.children else "  ")
        if node.kind in ("role", "profile"):
            if node.suited_to:
                lines.append(f"{detail}suited to: {node.suited_to}")
            lines.append(f"{detail}gate: {node.gate}")
            lines.append(f"{detail}skills: {', '.join(node.skills) or 'none'}")
        for index, child in enumerate(node.children):
            draw(child, below, index == len(node.children) - 1, False)

    draw(root, "", True, True)
    return "\n".join(lines) + "\n"


def main() -> int:
    """`python -m boss.roles.org`: print the firm as it is defined right now."""
    from boss.firm import FirmConfig
    from boss.roles import registry
    from boss.roles.builders import PROFILES

    print(render_org(org_chart(registry(), PROFILES, FirmConfig().profile)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
