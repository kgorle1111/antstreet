"""The contract every role is built on: a spec, one structured call with no tools, a ledger
record, and skills loaded from versioned files. No model calls: a fake `claude` plays the model."""

import json
import sys

import pytest

from boss.errors import Outcome
from boss.ledger import Billing, Event, EventType
from boss.roles import registry
from boss.roles.base import (
    DEPARTMENTS,
    RoleError,
    RoleOutputError,
    RoleSpec,
    call_role,
    ledger_fields,
    system_prompt,
)
from boss.skills import MAX_SKILL_CHARS, SkillError, all_skill_ids, load_skill, parse_skill
from boss.stream import Usage

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
FAKE = f"""#!{sys.executable}
import json, os, sys
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(sys.argv))
open(os.environ["FAKE_ARGV"] + ".thinking", "w").write(os.environ.get("MAX_THINKING_TOKENS", "-"))
print(os.environ["FAKE_OUTPUT"])
"""
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.0123,
    "modelUsage": {"m": {"inputTokens": 100, "outputTokens": 50, "cacheReadInputTokens": 7}},
}


def spec(**over) -> RoleSpec:
    fields = {
        "name": "tester",
        "department": "engineering",
        "reports_to": "boss",
        "purpose": "writes checks",
        "gate": "every check fails on an empty workspace",
        "prompt": "term_sheet_v1.md",
    }
    return RoleSpec(**fields | over)


@pytest.fixture
def call(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE)
    cli.chmod(0o755)
    argv_file = tmp_path / "argv.json"

    def run(output, role=None, **kwargs):
        text = output if isinstance(output, str) else json.dumps(output)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_ARGV": str(argv_file)}
        env |= {"FAKE_OUTPUT": text}
        return call_role(
            role or spec(),
            "Idea:\nx",
            SCHEMA,
            env=env,
            model="haiku",
            executable=str(cli),
            **kwargs,
        )

    run.argv = lambda: json.loads(argv_file.read_text())
    run.thinking = lambda: (tmp_path / "argv.json.thinking").read_text()
    return run


def test_a_role_call_has_no_tools_its_own_system_prompt_and_a_schema(call):
    out = call(RESULT | {"structured_output": {"answer": "ok"}})
    assert out.data == {"answer": "ok"}
    assert out.usage == Usage(12_300, 100, 50, 7)
    argv = call.argv()
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--system-prompt") + 1] == system_prompt(spec())
    assert json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
    assert argv[argv.index("--max-budget-usd") + 1] == "0.15"
    assert "--safe-mode" in argv and argv[-1] == "Idea:\nx"


def test_the_roles_own_cap_and_thinking_budget_reach_the_call(call):
    call(
        RESULT | {"structured_output": {"answer": "ok"}}, spec(cap_micros=40_000), thinking_tokens=0
    )
    argv = call.argv()
    assert argv[argv.index("--max-budget-usd") + 1] == "0.04"
    assert call.thinking() == "0"


@pytest.mark.parametrize(
    ("output", "outcome"),
    [
        (
            RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"},
            Outcome.LOGIN,
        ),
        (
            RESULT | {"subtype": "error_max_budget_usd", "terminal_reason": "budget_exhausted"},
            Outcome.CAPPED,
        ),
        ("not json at all", Outcome.CRASHED),
    ],
)
def test_a_failed_call_raises_with_its_outcome_and_whatever_it_cost(call, output, outcome):
    with pytest.raises(RoleError) as info:
        call(output)
    assert info.value.outcome is outcome and info.value.role == "tester"
    assert str(info.value).startswith("tester: ")


@pytest.mark.parametrize("structured", [None, "text", ["a"], 5])
def test_a_call_without_an_object_as_output_is_an_error_that_still_carries_its_cost(
    call, structured
):
    with pytest.raises(RoleError, match="no structured output") as info:
        call(RESULT | {"structured_output": structured})
    assert info.value.usage.cost_micros == 12_300


@pytest.mark.parametrize("prompt", ["", "   ", "--dangerously-skip-permissions", "\n-x"])
def test_a_prompt_that_is_empty_or_reads_as_a_flag_is_refused_before_any_call(prompt):
    with pytest.raises(ValueError, match="prompt"):
        call_role(spec(), prompt, SCHEMA, env={}, model="haiku", executable="/no/such/binary")


def test_a_missing_binary_is_a_role_error_of_unknown_cost():
    with pytest.raises(RoleError) as info:
        call_role(spec(), "x", SCHEMA, env={}, model="haiku", executable="/no/such/binary")
    assert info.value.usage.cost_micros is None


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "Tester"},
        {"name": "t"},
        {"name": "has space"},
        {"name": "role:x"},
        {"department": "marketing"},
        {"purpose": " "},
        {"gate": ""},
        {"cap_micros": 0},
        {"cap_micros": 1.5},
        {"cap_micros": True},
    ],
)
def test_an_invalid_spec_is_rejected(bad):
    with pytest.raises(ValueError):
        spec(**bad)


def test_every_spec_needs_a_gate_because_a_role_never_decides_by_itself():
    assert spec().gate and "gate" in RoleSpec.__dataclass_fields__
    assert spec().default_on is False  # off until a measurement says it earns its cost
    assert spec().actor == "role:tester"
    assert "product" in DEPARTMENTS and "advisory" in DEPARTMENTS


def test_an_output_that_fails_its_gate_lists_every_problem_and_keeps_the_cost():
    error = RoleOutputError(
        "tester", ["c01 passes on nothing", "S1.2 has no check"], Usage(9, 1, 1, 0)
    )
    assert error.problems == ["c01 passes on nothing", "S1.2 has no check"]
    assert error.outcome is Outcome.COMPLETED and error.usage.cost_micros == 9
    assert "c01 passes on nothing; S1.2 has no check" in str(error)
    assert error.data is None  # a gate that has no output to show says so


def test_a_refused_output_travels_with_the_error_so_it_can_be_kept():
    refused = {"checks": [{"id": "c01"}]}
    error = RoleOutputError("tester", ["c01 passes on nothing"], Usage(9, 1, 1, 0), refused)
    assert error.data is refused and error.role == "tester"


def test_ledger_fields_book_a_roles_spend_under_its_own_actor():
    role = spec(skills=())
    fields = ledger_fields(
        role, Usage(None, 3, 4, 5), "crashed", model="haiku", env={"HOME": "/h"}, purpose="checks"
    )
    event = Event(run="r", round=0, actor=role.actor, event=EventType.ROLE_CALL, **fields)
    assert event.cost_micros is None and event.billing is Billing.SUBSCRIPTION
    assert (event.tokens_in, event.tokens_out, event.tokens_cached) == (3, 4, 5)
    assert event.data == {
        "role": "tester",
        "model": "haiku",
        "prompt": "term_sheet_v1.md",
        "skills": [],
        "outcome": "crashed",
        "purpose": "checks",
    }
    assert Event.from_json(event.to_json()) == event


@pytest.mark.parametrize("actor", ["role:Tester", "role:", "role:a b", "role:x\n", "roles:x"])
def test_only_a_well_formed_role_actor_is_accepted_by_the_ledger(actor):
    with pytest.raises(ValueError):
        Event(run="r", round=0, actor=actor, event=EventType.ROLE_CALL)


def test_the_registry_collects_every_module_and_refuses_two_roles_with_one_name(monkeypatch):
    found = registry()
    for name, role in found.items():
        assert role.name == name and role.actor == f"role:{name}"
    import boss.roles as package

    fake = type("M", (), {"SPECS": (spec(name="dup"), spec(name="dup"))})
    monkeypatch.setattr(
        package.pkgutil, "iter_modules", lambda path: [type("I", (), {"name": "x"})]
    )
    monkeypatch.setattr(package.importlib, "import_module", lambda name: fake)
    with pytest.raises(ValueError, match="defined twice"):
        registry()


SKILL = (
    "---\nname: edge-cases\nversion: 2\ndescription: Find the edges.\n---\nList every boundary.\n"
)


def test_a_skill_file_parses_into_its_header_and_body():
    skill = parse_skill("tester/edge-cases", SKILL)
    assert (skill.id, skill.version, skill.description) == (
        "tester/edge-cases",
        2,
        "Find the edges.",
    )
    assert skill.text == "List every boundary."


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("List every boundary.", "header"),
        (SKILL.replace("version: 2\n", ""), "exactly"),
        (SKILL.replace("version: 2", "version: two"), "version"),
        (SKILL.replace("version: 2", "version: 0"), "version"),
        (SKILL.replace("name: edge-cases", "name: other"), "not the file's name"),
        (SKILL.replace("description: Find the edges.", "description:"), "description"),
        (SKILL.replace("List every boundary.\n", "\n"), "body"),
        (SKILL + "extra: x\n" * 0 + "y" * (MAX_SKILL_CHARS + 1), "over"),
        (
            SKILL.replace("---\nList", "author: me\n---\nList").replace(
                "description: Find the edges.\nauthor", "description: Find the edges.\nauthor"
            ),
            "header",
        ),
    ],
)
def test_a_malformed_skill_is_refused_with_the_reason(raw, message):
    with pytest.raises(SkillError, match=message):
        parse_skill("tester/edge-cases", raw)


@pytest.mark.parametrize(
    "bad", ["edge-cases", "../x/y", "tester/../../etc", "Tester/x", "a/b/c", ""]
)
def test_a_skill_id_cannot_name_a_file_outside_the_skills_folder(bad):
    with pytest.raises(SkillError):
        load_skill(bad)


def test_a_missing_skill_is_an_error_not_an_empty_prompt():
    with pytest.raises(SkillError, match="no skill"):
        load_skill("tester/does-not-exist")


def test_every_shipped_skill_loads_and_every_role_names_only_shipped_skills():
    shipped = all_skill_ids()
    for skill_id in shipped:
        assert load_skill(skill_id).id == skill_id
    for role in registry().values():
        assert set(role.skills) <= set(shipped), f"{role.name} names a skill that is not shipped"
        assert system_prompt(role).strip()
