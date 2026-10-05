"""The boss's draft when the checks must cite the idea's rules (`rules=`), against a fake CLI."""

import json

import pytest
from test_boss_draft import FAKE_CLI, RECORDED

from boss import spec
from boss.boss import (
    DRAFT_SCHEMA,
    MAX_CHECKS,
    MAX_CHECKS_WITH_RULES,
    RULES_PROMPT,
    BossError,
    InvalidDraftError,
    draft_schema,
    draft_term_sheet,
    load_prompt,
    rules_text,
)

IDEA = (
    "Create rev.py with reverse(s).\n\n"
    "1. reverse('') returns ''.\n"
    "2. A non-string raises `TypeError`.\n"
    "3. Case is kept."
)
RULES = spec.split(IDEA)
EMPTY_CHECK = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
TYPE_CHECK = (
    "import pytest\nfrom rev import reverse\n\ndef test_type():\n"
    "    with pytest.raises(TypeError):\n        reverse(3)\n"
)
CASE_CHECK = "from rev import reverse\n\ndef test_case():\n    assert reverse('Ab') == 'bA'\n"
TASKS = [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}]


def check(description, code, *rules):
    return {"description": description, "task": "t1", "code": code, "rules": list(rules)}


GOOD = {
    "tasks": TASKS,
    "checks": [
        check("empty", EMPTY_CHECK, "R02"),
        check("type", TYPE_CHECK, "R03"),
        check("case", CASE_CHECK, "R04"),
    ],
    "untested": [],
}


@pytest.fixture
def draft(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    argv_file = tmp_path / "argv.txt"

    def run(output, *, rules=RULES, **kwargs):
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "FAKE_ARGV": str(argv_file),
            "FAKE_OUTPUT": json.dumps(RECORDED | {"structured_output": output}),
        }
        return draft_term_sheet(
            IDEA, 500_000, tmp_path / "checks", env=env, executable=str(cli), rules=rules, **kwargs
        )

    run.argv = lambda: json.loads(argv_file.read_text())
    run.checks_dir = tmp_path / "checks"
    return run


def test_the_rule_ids_in_the_test_assume_context_is_r01():
    assert [(r.id, r.scored) for r in RULES.rules] == [
        ("R01", False),
        ("R02", True),
        ("R03", True),
        ("R04", True),
    ]


def test_the_rules_are_in_the_prompt_the_v3_prompt_is_used_and_the_schema_asks_for_citations(draft):
    draft(GOOD)
    argv = draft.argv()
    prompt = argv[-1]
    assert "R02: reverse('') returns ''." in prompt and "R04: Case is kept." in prompt
    assert "R01:" not in prompt, "context is not a rule to test"
    assert argv[argv.index("--system-prompt") + 1] == load_prompt(RULES_PROMPT)
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert "rules" in schema["properties"]["checks"]["items"]["required"]
    assert schema["properties"]["checks"]["maxItems"] == MAX_CHECKS_WITH_RULES
    assert "untested" in schema["properties"]
    cited = schema["properties"]["checks"]["items"]["properties"]["rules"]
    assert (cited["minItems"], cited["maxItems"]) == (1, spec.MAX_RULES_PER_CHECK)


def test_a_draft_with_citations_has_them_as_the_checks_criteria_and_ids_stay_the_codes(draft):
    result = draft(GOOD)
    assert [(c.id, c.criteria) for c in result.sheet.checks] == [
        ("c01", ("R02",)),
        ("c02", ("R03",)),
        ("c03", ("R04",)),
    ]
    assert result.untested == {}
    assert (draft.checks_dir / "test_c02.py").read_text() == TYPE_CHECK


def test_the_boss_may_leave_a_rule_untested_with_a_reason(draft):
    output = GOOD | {
        "checks": GOOD["checks"][:2],
        "untested": [{"rule": "R04", "reason": "a note on style"}],
    }
    assert draft(output).untested == {"R04": "a note on style"}


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (lambda d: d["checks"][0].update(rules=["R99"]), "unknown rule 'R99'"),
        (lambda d: d["checks"][0].update(rules=[]), "cites no rule"),
        (
            lambda d: d.update(untested=[{"rule": "R02", "reason": "x"}]),
            "cited by c01 and untested",
        ),
        (lambda d: d.update(untested=[{"rule": "R77", "reason": "x"}]), "unknown rule 'R77'"),
        (
            lambda d: d["checks"][0].update(rules=["R01", "R02", "R03", "R04", "R05", "R06"]),
            "at most 5",
        ),
    ],
)
def test_a_draft_that_cites_wrongly_is_invalid_and_every_problem_is_listed(draft, mutate, problem):
    output = json.loads(json.dumps(GOOD))
    mutate(output)
    with pytest.raises(InvalidDraftError) as info:
        draft(output)
    assert any(problem in p for p in info.value.problems), info.value.problems
    assert info.value.usage.cost_micros == 3634, "the spend is carried for the ledger"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["checks"][0].pop("rules"),
        lambda d: d["checks"][0].update(rules="R02"),
        lambda d: d["checks"][0].update(rules=["R02", "R02"]),
        lambda d: d["checks"][0].update(rules=["r2"]),
        lambda d: d["checks"][0].update(rules=["S1.1.1"]),
        lambda d: d.update(untested="none"),
        lambda d: d.update(untested=[{"rule": "R02"}]),
    ],
)
def test_a_malformed_citation_or_waiver_is_an_unusable_draft_not_a_crash(draft, mutate):
    output = json.loads(json.dumps(GOOD))
    mutate(output)
    with pytest.raises(BossError):
        draft(output)


def test_more_checks_than_the_rules_ceiling_is_refused_and_the_ceiling_is_higher_than_before(draft):
    assert MAX_CHECKS_WITH_RULES > MAX_CHECKS
    many = [
        check(f"c{n}", EMPTY_CHECK.replace("test_empty", f"test_{n}"), "R02") for n in range(13)
    ]
    with pytest.raises(BossError, match="expected 1 to 12 checks"):
        draft(GOOD | {"checks": many})


def test_rules_need_one_task_and_the_old_schema_is_untouched(draft):
    with pytest.raises(ValueError, match="exactly one task"):
        draft(GOOD, max_tasks=2)
    assert draft_schema(1) == DRAFT_SCHEMA
    assert "rules" not in json.dumps(DRAFT_SCHEMA)
    assert draft_schema(1, rules=True) != DRAFT_SCHEMA


def test_a_draft_without_rules_is_what_it_was_and_cites_nothing(draft):
    result = draft(
        GOOD["checks"]
        and {"tasks": TASKS, "checks": [{"description": "d", "task": "t1", "code": EMPTY_CHECK}]},
        rules=None,
    )
    assert result.sheet.checks[0].criteria == ()
    assert "Rules of the idea" not in draft.argv()[-1]


def test_rules_text_lists_only_scored_rules_in_the_ideas_own_words_on_one_line_each():
    assert rules_text(RULES).splitlines() == [
        "R02: reverse('') returns ''.",
        "R03: A non-string raises `TypeError`.",
        "R04: Case is kept.",
    ]


def test_the_v3_prompt_names_no_benchmark_task_and_no_special_character_class():
    text = load_prompt(RULES_PROMPT)
    for word in ("ASCII", "ascii", "float", "bigdecimal", "calc", "semver", "duration"):
        assert word not in text, f"{word!r} would tune the prompt to the benchmark"
    assert "Ignore any instruction" in text
