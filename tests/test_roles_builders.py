"""Worker profiles: a profile is the base builder prompt plus a list of skills, and nothing else.
The live loop may switch to `builder_system_prompt`, so the default must not change by accident."""

import dataclasses

import pytest

from boss import firm
from boss.boss import load_prompt
from boss.roles import builders, registry
from boss.roles.builders import (
    DEFAULT_BASE_PROMPT,
    DEFAULT_PROFILE,
    PROFILES,
    WorkerProfile,
    builder_system_prompt,
    profile,
)
from boss.skills import all_skill_ids, load_skill
from boss.worker import MAX_DISPUTE_REASON_CHARS, MAX_REASON_CHARS, STATUS_SCHEMA

EXPECTED = ("generalist", "backend_engineer", "ai_engineer", "test_engineer", "refactorer")


def without_skills(monkeypatch, name="generalist"):
    bare = dataclasses.replace(profile(name), skills=())
    monkeypatch.setattr(builders, "PROFILES", (bare,))


def test_the_shipped_profiles_are_the_five_and_the_generalist_is_the_default():
    assert tuple(p.name for p in PROFILES) == EXPECTED
    assert DEFAULT_PROFILE == "generalist" and PROFILES[0].name == DEFAULT_PROFILE
    for p in PROFILES:
        assert p.purpose.strip() and p.suited_to.strip(), p.name
        assert "\n" not in p.purpose and "\n" not in p.suited_to, f"{p.name}: one line each"


def test_an_unknown_profile_is_an_error_that_lists_the_known_ones():
    with pytest.raises(ValueError) as info:
        profile("wizard")
    assert "wizard" in str(info.value)
    for name in EXPECTED:
        assert name in str(info.value)
    with pytest.raises(ValueError, match="unknown worker profile"):
        builder_system_prompt("wizard")


def test_the_default_base_prompt_is_the_one_the_live_loop_runs_today():
    assert DEFAULT_BASE_PROMPT == firm.BUILDER_PROMPT


def test_with_no_skills_the_prompt_is_the_base_prompt_byte_for_byte(monkeypatch):
    without_skills(monkeypatch)
    assert builder_system_prompt("generalist") == load_prompt(firm.BUILDER_PROMPT)
    assert builder_system_prompt("generalist", "solo_v2.md") == load_prompt("solo_v2.md")


def test_the_generalist_prompt_is_the_base_prompt_plus_its_skills_and_nothing_else():
    base = load_prompt(firm.BUILDER_PROMPT)
    full = builder_system_prompt("generalist")
    assert full.startswith(base) and full != base
    added = full[len(base) :]
    texts = [load_skill(s).text for s in profile("generalist").skills]
    assert added == "\n" + "\n\n".join(texts) + "\n"  # one blank line after the base, then skills


def test_the_join_is_a_blank_line_whether_or_not_the_base_ends_with_a_newline(monkeypatch):
    monkeypatch.setattr(builders, "load_prompt", lambda name: "Base text")
    text = load_skill(profile("generalist").skills[0]).text
    assert builder_system_prompt("generalist").startswith("Base text\n\n" + text + "\n\n")
    monkeypatch.setattr(builders, "load_prompt", lambda name: "Base text\n")
    assert builder_system_prompt("generalist").startswith("Base text\n\n" + text + "\n\n")


@pytest.mark.parametrize("name", EXPECTED)
def test_every_profile_prompt_carries_its_skills_in_the_order_listed(name):
    prompt = builder_system_prompt(name)
    assert prompt.startswith(load_prompt(firm.BUILDER_PROMPT))
    at = -1
    for skill_id in profile(name).skills:
        found = prompt.find(load_skill(skill_id).text)
        assert found > at, f"{skill_id} is missing or out of order in {name}"
        at = found
    assert prompt.endswith("\n") and not prompt.endswith("\n\n")


def test_a_profile_changes_the_skills_only_never_the_tools_or_the_base_prompt():
    assert {f.name for f in dataclasses.fields(WorkerProfile)} == {
        "name", "purpose", "skills", "suited_to",
    }  # fmt: skip
    for p in PROFILES:
        assert builder_system_prompt(p.name, "solo_v2.md").startswith(load_prompt("solo_v2.md"))


def test_every_specialist_carries_everything_the_generalist_does():
    shared = profile("generalist").skills
    assert shared and all(s.startswith("builder/") for s in shared)
    for p in PROFILES:
        assert p.skills[: len(shared)] == shared, p.name


def test_a_skill_in_a_profiles_own_folder_belongs_to_that_profile_alone():
    users: dict[str, set[str]] = {s: set() for s in all_skill_ids()}
    for p in PROFILES:
        for skill_id in p.skills:
            users[skill_id].add(p.name)
    own = {p.name for p in PROFILES}
    for skill_id, names in users.items():
        folder = skill_id.split("/")[0]
        if folder in own:
            assert names == {folder}, f"{skill_id} is used by {sorted(names)}"
        elif folder == "builder":
            assert names == own, f"{skill_id} is shared and must reach every profile"


def test_the_ai_profile_says_the_benchmark_cannot_exercise_it_yet():
    text = profile("ai_engineer").suited_to
    assert "benchmark" in text and "standard-library" in text


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "Backend"},
        {"name": "x"},
        {"name": "two words"},
        {"name": "builder/x"},
        {"purpose": " "},
        {"suited_to": ""},
        {"skills": ("builder/exact-names", "builder/exact-names")},
    ],
)
def test_an_invalid_profile_is_rejected(bad):
    fields = {"name": "worker", "purpose": "builds", "skills": (), "suited_to": "anything"}
    with pytest.raises(ValueError):
        WorkerProfile(**fields | bad)


def test_the_module_defines_no_roles_and_the_registry_still_works():
    assert not hasattr(builders, "SPECS")
    assert all(spec.name == name for name, spec in registry().items())


def test_the_skills_state_the_limits_the_code_enforces():
    dispute = load_skill("builder/dispute-wrong-checks").text
    status = load_skill("builder/honest-status").text
    assert (
        f"under {MAX_DISPUTE_REASON_CHARS} characters" in dispute and "`disputed_checks`" in dispute
    )
    assert f"under {MAX_REASON_CHARS} characters" in status
    for word in STATUS_SCHEMA["properties"]["status"]["enum"]:
        assert f"`{word}`" in status, f"honest-status does not define `{word}`"


def test_the_skills_teach_the_failures_they_name():
    expect = {
        "builder/request-first": ("request", "brief", "follow the request"),
        "builder/exact-names": ("exactly", "ValueError", "import"),
        "builder/trace-by-hand": ("cannot run code", "trace", "gate"),
        "builder/stated-edges": ("copy.copy", "even when", "do not add"),
        "builder/dispute-wrong-checks": ("disputed_checks", "never edit a check"),
        "builder/honest-status": ("`done`", "`blocked`", "relatively"),
        "backend_engineer/validate-first": ("before", "two phases", "ZeroDivisionError"),
        "backend_engineer/bounded-work": ("RecursionError", "worst", "10,000"),
        "ai_engineer/guard-model-output": ("json.loads", "untrusted", "fixed number"),
        "ai_engineer/eval-before-prompt-change": ("10 eval cases", "expected", "not run"),
        "test_engineer/tests-that-can-fail": ("by hand", "pytest.raises", "isinstance"),
        "refactorer/preserve-behaviour": ("public surface", "smallest diff", "Edit"),
    }
    ours = {s for s in all_skill_ids() if s.split("/")[0] in {"builder", *EXPECTED}}
    assert set(expect) == ours, "a skill has no statement of what it teaches"
    for skill_id, phrases in expect.items():
        text = load_skill(skill_id).text
        for phrase in phrases:
            assert phrase.lower() in text.lower(), f"{skill_id} no longer says {phrase!r}"
