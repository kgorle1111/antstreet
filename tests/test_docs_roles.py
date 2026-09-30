"""docs/ROLES.md stays true: what it names exists, its tables match the code, and each way it says
to add a skill, a profile or a role works as written. It lists no specialist role by hand."""

import ast
import dataclasses
import re
import subprocess
import sys
import types

import pytest
from docs_support import DOCS, ROOT, code_spans, read, section, table
from skills_support import (
    BANNED_PHRASES,
    MAX_COMBINED_CHARS,
    combined_problems,
    skill_problems,
    usage_problems,
    users,
)

from boss import firm
from boss.boss import load_prompt
from boss.firm import FirmConfig
from boss.roles import builders, org, registry
from boss.roles.base import DEFAULT_ROLE_CAP_MICROS, DEPARTMENTS, RoleSpec
from boss.roles.builders import PROFILES, WorkerProfile, builder_system_prompt, profile
from boss.skills import MAX_SKILL_CHARS, SkillError, all_skill_ids, load_skill, parse_skill
from boss.termsheet import Task

DOC = DOCS / "ROLES.md"
BUILDER_SIDE = {p.name for p in PROFILES} | {"builder"}
PATH = re.compile(r"(?:src|tests|docs|bench)/[^\s`]*")


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def our_skills() -> list[str]:
    return [s for s in all_skill_ids() if s.split("/")[0] in BUILDER_SIDE]


def test_every_profile_and_every_builder_skill_is_named(text):
    named = set(code_spans(text))
    assert {p.name for p in PROFILES} <= named, "a profile is not named in docs/ROLES.md"
    assert set(our_skills()) <= named, "a builder skill is not named in docs/ROLES.md"


def test_every_file_the_document_mentions_exists(text):
    seen = 0
    for span in code_spans(text):
        for mention in PATH.findall(span):
            path = mention.split("::")[0].split("<")[0]  # a placeholder names its folder
            seen += 1
            assert (ROOT / path).exists(), f"docs/ROLES.md names {mention}, which does not exist"
            if "::" in mention:
                function = mention.split("::")[1]
                assert f"def {function}(" in read(ROOT / path), f"no test {mention}"
    assert seen >= 10


def test_the_profile_table_is_the_profile_registry(text):
    rows = table(section(text, "What a worker profile is"))
    assert [(r[0].strip("`"), r[1]) for r in rows] == [(p.name, p.purpose) for p in PROFILES]


def test_the_skill_table_names_each_shipped_builder_skill_once_with_the_failure_it_answers(text):
    rows = table(section(text, "What a skill is"))
    assert sorted(r[0].strip("`") for r in rows) == sorted(our_skills())
    assert all(len(r) == 2 and r[1] for r in rows)


def test_the_document_lists_no_specialist_role_and_says_where_the_list_comes_from(text):
    for spec in registry().values():
        assert f"`{spec.name}`" not in text, f"{spec.name} is listed by hand"
    assert "`render_org`" in text and "python -m boss.roles.org" in text
    assert "This document does not say which specialist roles exist" in text


def test_the_three_things_table_states_what_the_code_enforces(text):
    row = {r[0]: r for r in table(section(text, "Three different things"))}
    assert set(row) == {
        "What it is", "Defined in", "Tools", "Produces", "Paid for", "On by default",
    }  # fmt: skip
    assert "src/boss/roles/builders.py" in row["Defined in"][2]
    assert FirmConfig().profile is None  # no profile unless `--profile` names one
    assert "--profile" in row["On by default"][2] and "generalist" not in row["On by default"][2]
    assert RoleSpec("aa", "quality", "boss", "p", "g", "term_sheet_v1.md").default_on is False
    assert f"{DEFAULT_ROLE_CAP_MICROS:,} micro-dollars" in text


def test_the_rule_that_a_role_is_switched_on_by_a_measurement_is_stated(text):
    body = section(text, "A role is switched on by a measurement, not by an opinion")
    assert "default_on=True" in body and "measurement" in section(text, "What a role is")
    assert "D29" in body and "D26" in body
    decisions = read(DOCS / "DECISIONS.md")
    assert "### D29:" in decisions and "### D26:" in decisions


# --- add a skill -----------------------------------------------------------------------------

SKILL = "---\nname: my-skill\nversion: 1\ndescription: One idea.\n---\nRead the request first.\n"


def test_a_skill_built_by_the_steps_parses_and_passes_the_bar():
    skill = parse_skill("builder/my-skill", SKILL)
    assert skill_problems(skill) == []


def test_the_steps_header_rule_is_the_parsers(text):
    steps = section(text, "Add a skill")
    assert "exactly `name` (the file's name)" in steps and "`description`" in steps
    with pytest.raises(SkillError, match="exactly"):
        parse_skill("builder/my-skill", SKILL.replace("version: 1\n", ""))
    with pytest.raises(SkillError, match="not the file's name"):
        parse_skill("builder/other-name", SKILL)
    with pytest.raises(SkillError, match="version"):
        parse_skill("builder/my-skill", SKILL.replace("version: 1", "version: 0"))


def test_the_limits_and_banned_phrases_the_document_states_are_the_ones_enforced(text):
    assert f"under {MAX_SKILL_CHARS:,} characters" in text
    assert f"{MAX_COMBINED_CHARS:,} characters" in text
    bar = section(text, "What a skill is")
    for phrase in BANNED_PHRASES:
        assert f"`{phrase}`" in bar.lower(), f"the banned phrase {phrase!r} is not listed"


def test_a_skill_nobody_names_is_caught_and_naming_it_fixes_it():
    ids = [*all_skill_ids(), "builder/my-skill"]
    used = users()  # every role and every profile: a skill only a role names is used too
    assert usage_problems(ids, used) == [
        "builder/my-skill is used by no role and no profile: delete it or use it"
    ]
    used["profile:generalist"] += ("builder/my-skill",)
    assert usage_problems(ids, used) == []


def test_a_profile_over_the_combined_limit_is_caught():
    size = {"builder/my-skill": MAX_COMBINED_CHARS + 1}
    assert combined_problems({"profile:generalist": ("builder/my-skill",)}, size)


# --- add a worker profile --------------------------------------------------------------------


def test_a_profile_built_by_the_steps_is_available_and_carries_the_generalists_six(
    text, monkeypatch
):
    steps = section(text, "Add a worker profile")
    generalist = profile("generalist").skills
    assert len(generalist) == 6 and "the generalist's six" in steps
    own = (*generalist, "refactorer/preserve-behaviour")
    mine = WorkerProfile("data_engineer", "Moves data.", own, "Pipelines; not measured.")
    monkeypatch.setattr(builders, "PROFILES", (*PROFILES, mine))
    assert profile("data_engineer") is mine
    prompt = builder_system_prompt("data_engineer")
    assert prompt.startswith(load_prompt(firm.BUILDER_PROMPT))
    assert all(load_skill(skill).text in prompt for skill in mine.skills)
    with pytest.raises(ValueError, match="data_engineer"):
        profile("nobody")


def test_a_skill_named_in_a_profile_must_exist():
    ghost = WorkerProfile("ghost_writer", "Writes.", ("builder/does-not-exist",), "Nothing.")
    assert usage_problems(all_skill_ids(), {"profile:ghost_writer": ghost.skills}) != []


# --- add a role ------------------------------------------------------------------------------


def fields() -> dict:
    return {
        "name": "designer",
        "department": "product",
        "reports_to": "boss",
        "purpose": "sketches the screens",
        "gate": "every screen names a check",
        "prompt": "term_sheet_v1.md",
    }


def test_the_departments_and_fields_the_document_states_are_the_specs(text):
    names = [f"`{d}`" for d in DEPARTMENTS]
    assert ", ".join(names[:-1]) + f" or {names[-1]}" in " ".join(text.split())
    steps = section(text, "Add a role")
    for field in ("name", "department", "reports_to", "purpose", "gate", "prompt", "skills"):
        assert f"`{field}`" in steps, f"step 2 does not name {field}"
    assert "`cap_micros`" in steps and "`default_on=False`" in steps
    for bad in ({"name": "My Role"}, {"department": "sales"}, {"gate": ""}):
        with pytest.raises(ValueError):
            RoleSpec(**fields() | bad)


def test_a_role_built_by_the_steps_forms_a_tree_under_the_boss_and_is_off():
    spec = RoleSpec(**fields())
    assert spec.default_on is False
    assert org.org_problems({spec.name: spec}) == []
    assert "designer" in org.render_org(org.org_chart({spec.name: spec}, PROFILES))
    orphan = RoleSpec(**fields() | {"reports_to": "nobody"})
    assert org.org_problems({orphan.name: orphan}) == [
        "role designer reports to nobody, which is not a role"
    ]


def test_a_module_that_defines_specs_is_collected_and_one_that_does_not_is_ignored(monkeypatch):
    import boss.roles as package

    spec = RoleSpec(**fields())
    modules = {"designer": types.SimpleNamespace(SPECS=(spec,)), "builders": builders}
    monkeypatch.setattr(
        package.pkgutil,
        "iter_modules",
        lambda path: [types.SimpleNamespace(name=n) for n in modules],
    )
    monkeypatch.setattr(
        package.importlib, "import_module", lambda name: modules[name.split(".")[-1]]
    )
    assert registry() == {"designer": spec}


# --- see the whole organisation --------------------------------------------------------------


def test_the_command_the_document_gives_prints_the_organisation():
    run = subprocess.run(
        [sys.executable, "-m", "boss.roles.org"], cwd=ROOT, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.startswith("investor") and "generalist" in run.stdout
    for name in registry():
        assert name in run.stdout


def test_the_functions_the_document_names_exist(text):
    section_text = section(text, "See the whole organisation")
    for name in ("org_chart", "org_problems", "render_org"):
        assert f"`{name}" in section_text and callable(getattr(org, name))


def _imports_of_roles(path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(read(path))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("boss.roles"):
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def test_what_is_not_built_is_still_not_built(text):
    body = section(text, "Not built")
    live = read(ROOT / "src" / "boss" / "firm.py")
    # A profile is chosen once for the whole run, by the investor: the loop uses it when set.
    assert "return builder_system_prompt(self.config.profile, BUILDER_PROMPT)" in live
    assert "if self.config.profile is None:" in live and FirmConfig().profile is None
    assert '"profile": self.config.profile' in live  # every `hired` event names it
    # Nothing assigns a profile to a task: a task has no such field, the boss's draft has none.
    assert "profile" not in {f.name for f in dataclasses.fields(Task)}
    assert "profile" not in read(ROOT / "src" / "boss" / "boss.py")
    assert "Nothing assigns a profile to a task" in body
    # No role is called by `boss fund`: the loop and the command import no role module.
    allowed = {
        "boss.roles.registry",
        "boss.roles.builders.PROFILES",
        "boss.roles.builders.builder_system_prompt",
        "boss.roles.org.org_chart",
        "boss.roles.org.render_org",
    }
    for module in sorted((ROOT / "src" / "boss").glob("*.py")):
        assert _imports_of_roles(module) <= allowed, f"{module.name} now imports a role"
    assert "No role is called by `boss fund`" in body
