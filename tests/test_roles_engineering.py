"""The engineering roles: the system designer's gate, the tester's gate, the coverage matrix and
the staged pipeline. No model calls: a fake `claude` answers the designer and the tester
differently."""

import copy
import json
import sys
from dataclasses import replace

import pytest

from boss.errors import Outcome
from boss.roles import registry
from boss.roles.base import RoleError, RoleOutputError, system_prompt
from boss.roles.engineering import (
    SYSTEM_DESIGNER,
    TESTER,
    TESTS_SCHEMA,
    Design,
    DesignTask,
    StagedDraftError,
    TestPlan,
    Untestable,
    assemble_term_sheet,
    coverage,
    design_schema,
    design_tasks,
    design_text,
    draft_staged,
    render_coverage,
    stories_text,
    write_checks,
)
from boss.roles.stories import Stories, parse_stories, story_problems
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, TermSheet, validate

IDEA = (
    "Create slug.py with slugify(text). Lower-case the text and join words with single hyphens.\n"
    "Create wrap.py with wrap(text, width) -> list[str]. Break text into lines of at most width "
    "characters, only at spaces."
)
STORIES = parse_stories(
    {
        "stories": [
            {
                "id": "S1",
                "as_a": "developer",
                "i_want": "a slug from text",
                "so_that": "I can build URLs",
                "priority": "must",
                "criteria": [
                    {
                        "id": "S1.1",
                        "given": "text with spaces",
                        "when": "slugify is called",
                        "then": "words are joined with single hyphens",
                        "source": "join words with single hyphens",
                    },
                    {
                        "id": "S1.2",
                        "given": "mixed case text",
                        "when": "slugify is called",
                        "then": "the slug is lower case",
                        "source": "Lower-case the text",
                    },
                ],
            },
            {
                "id": "S2",
                "as_a": "developer",
                "i_want": "text wrapped to a width",
                "so_that": "it fits a terminal",
                "priority": "should",
                "criteria": [
                    {
                        "id": "S2.1",
                        "given": "long text and a width",
                        "when": "wrap is called",
                        "then": "no line is longer than the width",
                        "source": "lines of at most width characters",
                    },
                    {
                        "id": "S2.2",
                        "given": "a line that needs breaking",
                        "when": "wrap is called",
                        "then": "it breaks only at spaces",
                        "source": "only at spaces",
                    },
                ],
            },
        ],
        "out_of_scope": ["hyphenation"],
    }
)
DESIGN = {
    "tasks": [
        {
            "id": "t1",
            "brief": "Create slug.py: lower-case the text and join its words with hyphens.",
            "paths": ["slug.py"],
            "stories": ["S1"],
            "interfaces": ["slugify(text)"],
        },
        {
            "id": "t2",
            "brief": "Create wrap.py: break text into lines of at most width characters.",
            "paths": ["wrap.py"],
            "stories": ["S2"],
            "interfaces": ["wrap(text, width) -> list[str]"],
        },
    ]
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.0123,
    "modelUsage": {"m": {"inputTokens": 100, "outputTokens": 50, "cacheReadInputTokens": 7}},
}
USAGE = Usage(12_300, 100, 50, 7)
FAKE = f"""#!{sys.executable}
import json, os, sys
argv = sys.argv
system = argv[argv.index("--system-prompt") + 1]
role = "designer" if system.startswith("You are the system designer") else "tester"
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({{"role": role, "argv": argv}}) + "\\n")
print(os.environ["FAKE_" + role.upper()])
"""


def answer(structured) -> str:
    return json.dumps(RESULT | {"structured_output": structured})


@pytest.fixture
def cli(tmp_path):
    """A fake `claude` that answers by role and logs each call's argv."""
    exe = tmp_path / "fake-claude"
    exe.write_text(FAKE)
    exe.chmod(0o755)
    log = tmp_path / "calls.jsonl"

    class Fake:
        executable = str(exe)
        checks_dir = tmp_path / "checks"
        answers = {"DESIGNER": answer(DESIGN), "TESTER": answer({})}

        @property
        def env(self):
            env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_LOG": str(log)}
            return env | {f"FAKE_{k}": v for k, v in self.answers.items()}

        def designer(self, output):
            self.answers["DESIGNER"] = output if isinstance(output, str) else answer(output)

        def tester(self, output):
            self.answers["TESTER"] = output if isinstance(output, str) else answer(output)

        @property
        def calls(self):
            return (
                [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            )

    return Fake()


def design_of(cli, output, *, max_tasks=2, stories=STORIES):
    cli.designer(output)
    return design_tasks(
        IDEA, stories, max_tasks=max_tasks, env=cli.env, model="haiku", executable=cli.executable
    )


def edited(path, value, base=DESIGN):
    data = copy.deepcopy(base)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


def design_problems_of(cli, output, **kwargs) -> list[str]:
    with pytest.raises(RoleOutputError) as info:
        design_of(cli, output, **kwargs)
    assert info.value.usage == USAGE and info.value.role == "system_designer"
    return info.value.problems


# --- the stories the fixtures use are themselves good ---------------------------------------


def test_the_fixture_stories_pass_their_own_gate():
    assert story_problems(STORIES, IDEA) == []


# --- system designer: the call ---------------------------------------------------------------


def test_the_designer_is_a_no_tools_call_with_its_own_prompt_schema_and_the_stories(cli):
    design, usage = design_of(cli, DESIGN)
    assert usage == USAGE
    assert [t.id for t in design.tasks] == ["t1", "t2"]
    assert design.tasks[1] == DesignTask(
        "t2",
        "Create wrap.py: break text into lines of at most width characters.",
        ("wrap.py",),
        ("S2",),
        ("wrap(text, width) -> list[str]",),
    )
    [call] = cli.calls
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--system-prompt") + 1] == system_prompt(SYSTEM_DESIGNER)
    assert json.loads(argv[argv.index("--json-schema") + 1]) == design_schema(2)
    assert argv[argv.index("--max-budget-usd") + 1] == "0.15"
    prompt = argv[-1]
    assert prompt.startswith("Idea:\nCreate slug.py")
    assert stories_text(STORIES) in prompt and prompt.endswith("Use at most 2 tasks.")


def test_the_designers_prompt_and_skills_are_shipped_and_ordered():
    prompt = system_prompt(SYSTEM_DESIGNER)
    assert prompt.startswith("You are the system designer")
    assert SYSTEM_DESIGNER.department == "engineering" and SYSTEM_DESIGNER.reports_to == "boss"
    assert registry()["system_designer"] is SYSTEM_DESIGNER
    assert SYSTEM_DESIGNER.default_on is False
    assert len(SYSTEM_DESIGNER.skills) >= 2


def test_the_schema_limits_the_number_of_tasks_to_what_the_caller_allows():
    schema = design_schema(3)
    assert schema["properties"]["tasks"]["maxItems"] == 3
    item = schema["properties"]["tasks"]["items"]
    assert set(item["required"]) == {"id", "brief", "paths", "stories", "interfaces"}
    assert item["properties"]["paths"]["minItems"] == 1


def test_stories_are_shown_to_the_roles_compactly_with_their_quotes():
    assert stories_text(STORIES).splitlines()[:4] == [
        "S1 [must] As a developer, I want a slug from text, so that I can build URLs.",
        "  S1.1 given text with spaces; when slugify is called; "
        "then words are joined with single hyphens",
        '      idea says: "join words with single hyphens"',
        "  S1.2 given mixed case text; when slugify is called; then the slug is lower case",
    ]
    assert stories_text(STORIES).splitlines()[-1] == "Out of scope: hyphenation"


def test_a_task_hands_the_builder_its_interfaces_in_the_brief():
    task = design_task_of(DESIGN["tasks"][0]).as_task()
    assert task.id == "t1" and task.paths == ("slug.py",)
    assert task.brief == (
        "Create slug.py: lower-case the text and join its words with hyphens."
        "\n\nPublic interface, exactly:\n- slugify(text)"
    )
    bare = design_task_of(DESIGN["tasks"][0] | {"interfaces": []}).as_task()
    assert bare.brief == "Create slug.py: lower-case the text and join its words with hyphens."


def design_task_of(raw) -> DesignTask:
    return DesignTask(
        raw["id"],
        raw["brief"],
        tuple(raw["paths"]),
        tuple(raw["stories"]),
        tuple(raw["interfaces"]),
    )


def test_the_owner_of_a_story_is_the_task_that_delivers_it():
    design = Design(tuple(design_task_of(t) for t in DESIGN["tasks"]))
    assert (design.owner_of("S1"), design.owner_of("S2"), design.owner_of("S9")) == (
        "t1",
        "t2",
        None,
    )


def test_a_failed_designer_call_raises_a_role_error_with_its_outcome(cli):
    login = RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"}
    with pytest.raises(RoleError) as info:
        design_of(cli, json.dumps(login))
    assert info.value.outcome is Outcome.LOGIN and not isinstance(info.value, RoleOutputError)


@pytest.mark.parametrize("max_tasks", [0, -1])
def test_a_designer_that_may_use_no_task_is_refused_before_any_call(cli, max_tasks):
    with pytest.raises(ValueError, match="max_tasks"):
        design_of(cli, DESIGN, max_tasks=max_tasks)
    assert cli.calls == []


# --- system designer: the gate ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "kwargs", "expected"),
    [
        (DESIGN, {"max_tasks": 1}, "needs 1 to 1 tasks, has 2"),
        ({"tasks": []}, {}, "needs 1 to 2 tasks, has 0"),
        (edited(["tasks", 1, "id"], "t 1"), {}, "task id 't 1' is invalid"),
        (edited(["tasks", 1, "id"], "t1"), {}, "duplicate task id 't1'"),
        (edited(["tasks", 0, "brief"], "  "), {}, "task t1 has an empty brief"),
        (
            edited(["tasks", 0, "paths"], ["../slug.py"]),
            {},
            "task t1 path '../slug.py' must stay inside the workspace",
        ),
        (
            edited(["tasks", 0, "paths"], ["/etc/x.py"]),
            {},
            "task t1 path '/etc/x.py' must stay inside the workspace",
        ),
        (edited(["tasks", 0, "paths"], []), {}, "task t1 declares no paths"),
        (edited(["tasks", 1, "paths"], ["slug.py"]), {}, "tasks t1 and t2 both own slug.py"),
        (edited(["tasks", 1, "paths"], ["."]), {}, "tasks t1 and t2 both own ."),
        (edited(["tasks", 0, "stories"], ["S1", "S9"]), {}, "task t1 names unknown story 'S9'"),
        (
            edited(["tasks", 1, "stories"], ["S1", "S2"]),
            {},
            "story S1 must belong to exactly one task, is in: t1, t2",
        ),
        (
            edited(["tasks", 0, "stories"], ["S1", "S1"]),
            {},
            "story S1 must belong to exactly one task, is in: t1, t1",
        ),
        (
            edited(["tasks", 1, "stories"], ["S3"]),
            {},
            "story S2 must belong to exactly one task, is in: no task",
        ),
        (edited(["tasks", 1, "stories"], []), {}, "task t2 delivers no story"),
    ],
    ids=[
        "too-many",
        "none",
        "bad-id",
        "duplicate-id",
        "empty-brief",
        "escaping-path",
        "absolute-path",
        "no-paths",
        "shared-file",
        "root-path",
        "unknown-story",
        "story-in-two-tasks",
        "story-twice-in-one",
        "story-nowhere",
        "task-without-story",
    ],
)
def test_each_class_of_bad_design_is_named_and_the_usage_is_kept(cli, output, kwargs, expected):
    assert expected in design_problems_of(cli, output, **kwargs)


def test_a_directory_and_a_file_inside_it_may_not_belong_to_two_tasks(cli):
    data = edited(["tasks", 0, "paths"], ["pkg"])
    data["tasks"][1]["paths"] = ["pkg/wrap.py"]
    assert "tasks t1 and t2 both own pkg" in design_problems_of(cli, data)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ({"tasks": "t1"}, ["tasks must be a list"]),
        ({}, ["tasks must be a list"]),
        ({"tasks": [None]}, [f"task 1: {k} must be text" for k in ("id", "brief")]),
        (
            edited(["tasks", 0, "paths"], "slug.py"),
            ["task 1: paths must be a list of text"],
        ),
        (
            edited(["tasks", 1, "stories"], ["S2", 2]),
            ["task 2: stories must be a list of text"],
        ),
        (edited(["tasks", 0, "id"], 7), ["task 1: id must be text"]),
    ],
    ids=["not-a-list", "missing", "not-objects", "paths-text", "stories-mixed", "id-number"],
)
def test_an_output_that_is_not_shaped_like_a_design_is_reported_not_crashed_on(
    cli, output, expected
):
    found = design_problems_of(cli, output)
    assert all(p in found for p in expected)
    assert not any("story" in p and "exactly one" in p for p in found)  # no cascade


def test_every_designer_problem_is_reported_at_once(cli):
    data = edited(["tasks", 0, "paths"], ["../a.py"])
    data["tasks"][0]["brief"] = ""
    data["tasks"][1]["stories"] = ["S1", "S7"]
    found = design_problems_of(cli, data)
    assert len(found) >= 5
    assert "task t1 has an empty brief" in found
    assert "task t2 names unknown story 'S7'" in found
    assert "story S2 must belong to exactly one task, is in: no task" in found
    assert "story S1 must belong to exactly one task, is in: t1, t2" in found
    assert any("path '../a.py' must stay inside" in p for p in found)


def test_a_single_task_design_is_fine_when_one_task_is_all_that_is_allowed(cli):
    one = {
        "tasks": [DESIGN["tasks"][0] | {"stories": ["S1", "S2"], "paths": ["slug.py", "wrap.py"]}]
    }
    design, _ = design_of(cli, one, max_tasks=1)
    assert design.tasks[0].stories == ("S1", "S2")


# --- tester: the call and the files ------------------------------------------------------------

SLUG_JOIN = (
    "from slug import slugify\n\ndef test_joins():\n"
    "    assert slugify('Hi   there') == 'hi-there'\n"
)
SLUG_LOWER = "from slug import slugify\n\ndef test_lower():\n    assert slugify('ABC') == 'abc'\n"
WRAP_WIDTH = (
    "from wrap import wrap\n\ndef test_width():\n"
    "    assert all(len(line) <= 5 for line in wrap('aa bb cc dd', 5))\n"
)
TESTS = {
    "checks": [
        {
            "criteria": ["S1.1"],
            "task": "t1",
            "description": "words are joined with single hyphens",
            "code": SLUG_JOIN,
        },
        {
            "criteria": ["S1.2"],
            "task": "t1",
            "description": "the slug is lower case",
            "code": SLUG_LOWER,
        },
        {
            "criteria": ["S2.1"],
            "task": "t2",
            "description": "no line is longer than the width",
            "code": WRAP_WIDTH,
        },
    ],
    "untestable": [{"criterion": "S2.2", "reason": "not visible apart from S2.1"}],
}


def design_obj() -> Design:
    return Design(tuple(design_task_of(t) for t in DESIGN["tasks"]))


def checks_of(cli, output, *, design=None):
    cli.tester(output)
    return write_checks(
        IDEA,
        STORIES,
        design or design_obj(),
        cli.checks_dir,
        env=cli.env,
        model="haiku",
        executable=cli.executable,
    )


def test_good_checks_become_files_and_a_plan_whose_ids_and_names_are_ours(cli):
    plan, usage = checks_of(cli, TESTS)
    assert usage == USAGE
    assert [(c.id, c.file, c.task, c.criteria) for c in plan.checks] == [
        ("c01", "test_c01.py", "t1", ("S1.1",)),
        ("c02", "test_c02.py", "t1", ("S1.2",)),
        ("c03", "test_c03.py", "t2", ("S2.1",)),
    ]
    assert plan.checks[0].description == "words are joined with single hyphens"
    assert plan.untestable == (Untestable("S2.2", "not visible apart from S2.1"),)
    assert (cli.checks_dir / "test_c01.py").read_text() == SLUG_JOIN
    assert (cli.checks_dir / "test_c03.py").read_text() == WRAP_WIDTH
    assert sorted(p.name for p in cli.checks_dir.iterdir()) == [f"test_c0{n}.py" for n in (1, 2, 3)]


def test_the_tester_is_a_no_tools_call_that_sees_the_idea_stories_and_design(cli):
    checks_of(cli, TESTS)
    [call] = cli.calls
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--system-prompt") + 1] == system_prompt(TESTER)
    assert json.loads(argv[argv.index("--json-schema") + 1]) == TESTS_SCHEMA
    assert argv[argv.index("--max-budget-usd") + 1] == "0.25"
    prompt = argv[-1]
    assert prompt.startswith("Idea:\nCreate slug.py")
    assert stories_text(STORIES) in prompt and design_text(design_obj()) in prompt
    assert prompt.endswith("Write at most 16 checks.")


def test_the_design_is_shown_to_the_tester_with_files_stories_and_interfaces():
    assert design_text(design_obj()).splitlines()[:4] == [
        "t1: Create slug.py: lower-case the text and join its words with hyphens.",
        "  owns: slug.py",
        "  delivers: S1",
        "  interface: slugify(text)",
    ]


def test_the_testers_spec_prompt_and_skills_ship_and_it_reports_to_the_designer():
    assert TESTER.department == "engineering" and TESTER.reports_to == "system_designer"
    assert registry()["tester"] is TESTER and TESTER.default_on is False
    assert system_prompt(TESTER).startswith("You are the tester")
    assert "tester/only-what-the-idea-states" in TESTER.skills and len(TESTER.skills) >= 2
    assert TestPlan.__test__ is False


def test_an_id_or_file_name_offered_by_the_model_is_never_used(cli, tmp_path):
    hostile = copy.deepcopy(TESTS)
    hostile["checks"][0] |= {"id": "../../evil", "file": "../evil.py"}
    plan, _ = checks_of(cli, hostile)
    assert [c.id for c in plan.checks] == ["c01", "c02", "c03"]
    assert not (tmp_path / "evil.py").exists() and not (tmp_path.parent / "evil.py").exists()


def test_sixteen_checks_are_allowed_and_a_criterion_may_have_several(cli):
    many = copy.deepcopy(TESTS)
    many["checks"] += [dict(many["checks"][0], criteria=["S1.1", "S1.2"]) for _ in range(13)]
    plan, _ = checks_of(cli, many)
    assert plan.checks[-1].id == "c16" and plan.checks[-1].criteria == ("S1.1", "S1.2")


def test_a_failed_tester_call_raises_a_role_error_and_writes_nothing(cli):
    login = RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"}
    with pytest.raises(RoleError) as info:
        checks_of(cli, json.dumps(login))
    assert info.value.outcome is Outcome.LOGIN and info.value.role == "tester"
    assert not cli.checks_dir.exists()


def test_a_directory_that_cannot_be_written_is_a_role_error_that_keeps_the_usage(cli, tmp_path):
    (tmp_path / "blocker").write_text("a file, not a directory")
    cli.tester(TESTS)
    with pytest.raises(RoleError, match="cannot write the check files") as info:
        write_checks(
            IDEA,
            STORIES,
            design_obj(),
            tmp_path / "blocker" / "checks",
            env=cli.env,
            model="haiku",
            executable=cli.executable,
        )
    assert info.value.usage == USAGE and info.value.outcome is Outcome.COMPLETED


# --- tester: the gate --------------------------------------------------------------------------


def edited_tests(path, value):
    return edited(path, value, base=TESTS)


def rejected_by_tester(cli, output, **kwargs) -> list[str]:
    with pytest.raises(RoleOutputError) as info:
        checks_of(cli, output, **kwargs)
    assert info.value.usage == USAGE and info.value.role == "tester"
    return info.value.problems


def three_checks_for_the_first_story():
    checks = [
        TESTS["checks"][0],
        TESTS["checks"][1],
        dict(TESTS["checks"][0], criteria=["S1.1"]),
    ]
    return TESTS | {"checks": checks}


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            edited_tests(["checks", 0, "criteria"], ["S1.1", "S9.9"]),
            "check c01 cites unknown criterion 'S9.9'",
        ),
        (
            edited_tests(["checks", 0, "task"], "t9"),
            "check c01 belongs to unknown task 't9'",
        ),
        (
            edited_tests(["checks", 2, "task"], "t1"),
            "check c03 belongs to t1 but S2.1 is delivered by t2",
        ),
        (edited_tests(["checks", 0, "criteria"], []), "check c01 cites no criterion"),
        (
            edited_tests(["checks", 0, "criteria"], ["S1.1", "S1.1"]),
            "check c01 cites a criterion twice",
        ),
        (edited_tests(["checks", 0, "description"], "  "), "check c01 has no description"),
        (
            edited_tests(["untestable"], []),
            "criterion S2.2 has no check and is not listed untestable",
        ),
        (
            edited_tests(
                ["untestable"], TESTS["untestable"] + [{"criterion": "S1.1", "reason": "x"}]
            ),
            "S1.1 is covered by c01 and also listed untestable",
        ),
        (
            edited_tests(["untestable"], TESTS["untestable"] * 2),
            "S2.2 is listed untestable twice",
        ),
        (
            edited_tests(["untestable"], [{"criterion": "S7.7", "reason": "x"}]),
            "untestable names unknown criterion 'S7.7'",
        ),
        (
            edited_tests(["untestable", 0, "reason"], " "),
            "untestable S2.2 has no reason",
        ),
        (
            edited_tests(["checks"], TESTS["checks"] * 6),
            "needs 1 to 16 checks, has 18",
        ),
        (edited_tests(["checks"], []), "needs 1 to 16 checks, has 0"),
        (
            TESTS
            | {
                "checks": TESTS["checks"][:2],
                "untestable": [
                    {"criterion": "S2.1", "reason": "x"},
                    {"criterion": "S2.2", "reason": "y"},
                ],
            },
            "task t2 has no check, so its progress cannot be measured",
        ),
    ],
    ids=[
        "unknown-criterion",
        "unknown-task",
        "wrong-task",
        "no-criterion",
        "criterion-twice",
        "no-description",
        "uncovered",
        "covered-and-untestable",
        "untestable-twice",
        "untestable-unknown",
        "untestable-no-reason",
        "too-many",
        "none",
        "task-without-check",
    ],
)
def test_each_class_of_bad_checks_is_named_and_the_usage_is_kept(cli, output, expected):
    assert expected in rejected_by_tester(cli, output)
    assert not cli.checks_dir.exists() or not any(cli.checks_dir.iterdir())


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("def test_x(:\n    pass\n", "check c01 has a syntax error: line 1"),
        ("from slug import slugify\n", "check c01 defines no test_ function"),
        ("", "check c01 defines no test_ function"),
    ],
    ids=["syntax-error", "no-test", "empty"],
)
def test_a_check_file_that_is_not_a_pytest_file_is_rejected_and_removed(cli, code, expected):
    found = rejected_by_tester(cli, edited_tests(["checks", 0, "code"], code))
    assert any(p.startswith(expected) for p in found)
    assert list(cli.checks_dir.iterdir()) == []  # the files written for the attempt are gone


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ({"checks": "c"}, "checks must be a list"),
        ({"checks": [], "untestable": "none"}, "untestable must be a list"),
        (
            edited_tests(["checks", 0, "criteria"], "S1.1"),
            "check 1: criteria must be a list of text",
        ),
        (edited_tests(["checks", 1, "code"], 5), "check 2: code must be text"),
        (edited_tests(["checks", 2, "task"], None), "check 3: task must be text"),
        (edited_tests(["checks", 0, "code"], "x = '\ud800'"), "check 1: code is not valid text"),
        (edited_tests(["untestable", 0, "reason"], 3), "untestable 1: reason must be text"),
        (edited_tests(["checks", 0], "not an object"), "check 1: code must be text"),
    ],
    ids=[
        "checks-not-list",
        "untestable-not-list",
        "criteria-text",
        "code-number",
        "task-none",
        "lone-surrogate",
        "reason-number",
        "check-not-object",
    ],
)
def test_output_not_shaped_like_checks_is_reported_and_nothing_is_gated_or_written(
    cli, output, expected
):
    found = rejected_by_tester(cli, output)
    assert expected in found
    assert not any("has no check" in p for p in found)
    assert not cli.checks_dir.exists()


def test_every_tester_problem_is_reported_at_once(cli):
    output = edited_tests(["checks", 0, "task"], "t2")  # wrong task for S1.1
    output["checks"][1]["criteria"] = ["S4.4"]  # unknown, so S1.2 has no check either
    output["untestable"] = []  # and S2.2 has none
    assert sorted(rejected_by_tester(cli, output)) == [
        "check c01 belongs to t2 but S1.1 is delivered by t1",
        "check c02 cites unknown criterion 'S4.4'",
        "criterion S1.2 has no check and is not listed untestable",
        "criterion S2.2 has no check and is not listed untestable",
    ]


# --- the coverage matrix ---------------------------------------------------------------------


def spec(check_id, criteria, task="t1"):
    return CheckSpec(check_id, "d", f"test_{check_id}.py", task, tuple(criteria))


HAND_WORKED = [
    spec("c01", ["S1.1", "S1.2"]),
    spec("c02", ["S1.2"]),
    spec("c03", ["S2.1"], "t2"),
]


def test_coverage_maps_each_criterion_to_the_checks_that_cite_it_in_check_order():
    assert coverage(STORIES, HAND_WORKED) == {
        "S1.1": ("c01",),
        "S1.2": ("c01", "c02"),
        "S2.1": ("c03",),
        "S2.2": (),
    }
    assert coverage(STORIES, HAND_WORKED[::-1])["S1.2"] == ("c02", "c01")
    assert list(coverage(STORIES, HAND_WORKED)) == ["S1.1", "S1.2", "S2.1", "S2.2"]


def test_coverage_ignores_criteria_the_stories_do_not_have_and_lists_uncovered_ones():
    found = coverage(STORIES, [spec("c01", ["S9.9"])])
    assert found == {"S1.1": (), "S1.2": (), "S2.1": (), "S2.2": ()}
    assert coverage(STORIES, []) == found


def test_the_matrix_has_one_line_per_criterion_and_a_summary_read_from_the_plan():
    assert render_coverage(
        STORIES, HAND_WORKED, [Untestable("S2.2", "not visible apart from S2.1")]
    ).splitlines() == [
        "S1.1 words are joined with single hyphens                  c01",
        "S1.2 the slug is lower case                                c01, c02",
        "S2.1 no line is longer than the width                      c03",
        "S2.2 it breaks only at spaces                              "
        "UNTESTABLE: not visible apart from S2.1",
        "4 criteria: 3 covered, 1 untestable, 0 with no check",
    ]


def test_a_criterion_with_no_check_and_no_reason_is_shown_as_such_not_hidden():
    lines = render_coverage(STORIES, HAND_WORKED[:1], []).splitlines()
    assert lines[2].endswith("NO CHECK") and lines[3].endswith("NO CHECK")
    assert lines[-1] == "4 criteria: 2 covered, 0 untestable, 2 with no check"


def hostile_stories() -> Stories:
    data = STORIES.to_data()
    criteria = data["stories"][0]["criteria"]
    criteria[0]["then"] = "\x1b[31mred\x1b[0m sk-ant-api03-" + "A" * 40
    criteria[1]["then"] = "a\nb\t" + "long " * 200
    return parse_stories(data)


def test_hostile_model_text_is_made_safe_flat_and_narrow():
    reason = "why\n\x1b]0;title\x07 " + "x" * 300 + "\u202e"
    checks = [spec(f"c{n:02d}", ["S1.2"]) for n in range(1, 17)]
    out = render_coverage(hostile_stories(), checks, [Untestable("S2.2", reason)])
    lines = out.splitlines()
    assert len(lines) == 5  # four criteria and the summary: no model newline made another line
    assert all(len(line) < 100 for line in lines)
    assert "\x1b" not in out and "\x07" not in out and "\u202e" not in out
    assert lines[0].startswith("S1.1 \\x1b[31mred\\x1b[0m [REDACTED]")
    assert "sk-ant-api03" not in out
    assert lines[1].startswith("S1.2 a b long long") and "[cut]" in lines[1]
    assert lines[1].endswith("c01, c02, c03, c04, c05, c06, c07, [cut]")
    assert lines[3].endswith("[cut]") and "UNTESTABLE: why" in lines[3]


def test_a_criterion_id_from_the_model_is_made_safe_too():
    data = STORIES.to_data()
    data["stories"][0]["criteria"][0]["id"] = "S1.1\x1b[2J"
    out = render_coverage(parse_stories(data), [], [])
    assert "\x1b" not in out and out.splitlines()[0].startswith("S1 [cut] words")


def test_a_run_with_no_stories_has_an_empty_matrix():
    assert render_coverage(Stories(()), [], []) == (
        "0 criteria: 0 covered, 0 untestable, 0 with no check"
    )


# --- the staged pipeline and the assembled term sheet --------------------------------------------


def staged(cli, **kwargs):
    kwargs = {"stories": STORIES, "max_tasks": 2} | kwargs
    return draft_staged(
        IDEA,
        500_000,
        cli.checks_dir,
        env=cli.env,
        model="haiku",
        executable=cli.executable,
        **kwargs,
    )


def test_a_staged_draft_runs_the_designer_then_the_tester_and_returns_a_valid_sheet(cli):
    cli.designer(DESIGN)
    cli.tester(TESTS)
    draft = staged(cli)
    assert [call["role"] for call in cli.calls] == ["designer", "tester"]
    assert draft.designer_usage == USAGE and draft.tester_usage == USAGE
    assert draft.design == design_obj() and len(draft.plan.checks) == 3
    sheet = draft.sheet
    assert not sheet.approved_by_investor
    assert sheet.idea == IDEA and sheet.budget_micros == 500_000
    assert sheet.rounds == (Round(1, 500_000, 3),)
    assert [(c.id, c.task, c.criteria) for c in sheet.checks] == [
        ("c01", "t1", ("S1.1",)),
        ("c02", "t1", ("S1.2",)),
        ("c03", "t2", ("S2.1",)),
    ]
    assert [t.id for t in sheet.tasks] == ["t1", "t2"]
    assert sheet.tasks[1].brief.endswith(
        "Public interface, exactly:\n- wrap(text, width) -> list[str]"
    )
    assert sheet.tasks[0].paths == ("slug.py",)
    validate(sheet, cli.checks_dir)
    assert TermSheet.from_json(sheet.to_json()) == sheet
    assert json.loads(sheet.to_json())["checks"][2]["criteria"] == ["S2.1"]


def test_the_tester_is_shown_the_design_the_designer_produced(cli):
    renamed = edited(["tasks", 0, "brief"], "Create slug.py: a marker only the designer wrote.")
    cli.designer(renamed)
    cli.tester(TESTS)
    staged(cli)
    designer_call, tester_call = cli.calls
    assert "marker only the designer wrote" not in designer_call["argv"][-1]
    assert "marker only the designer wrote" in tester_call["argv"][-1]
    assert (
        designer_call["argv"][designer_call["argv"].index("--system-prompt") + 1]
        != (tester_call["argv"][tester_call["argv"].index("--system-prompt") + 1])
    )


def test_a_designer_that_fails_its_gate_stops_the_pipeline_after_one_paid_call(cli):
    cli.designer(edited(["tasks", 0, "stories"], []))
    with pytest.raises(StagedDraftError) as info:
        staged(cli)
    error = info.value
    assert error.stage == "system_designer" and error.outcome is Outcome.COMPLETED
    assert "task t1 delivers no story" in error.problems
    assert error.paid == {"system_designer": USAGE}
    assert isinstance(error.__cause__, RoleOutputError)
    assert [call["role"] for call in cli.calls] == ["designer"]
    assert not cli.checks_dir.exists()


def test_a_designer_call_that_fails_reports_how_it_ended(cli):
    capped = RESULT | {"subtype": "error_max_budget_usd", "terminal_reason": "budget_exhausted"}
    cli.designer(json.dumps(capped))
    with pytest.raises(StagedDraftError) as info:
        staged(cli)
    assert info.value.stage == "system_designer" and info.value.outcome is Outcome.CAPPED
    assert info.value.paid == {"system_designer": USAGE}
    assert info.value.problems == [f"boss call ended as {Outcome.CAPPED}"]


def test_a_tester_failure_carries_the_usage_of_the_designer_that_was_already_paid(cli):
    cli.designer(DESIGN)
    cli.tester(edited_tests(["checks", 0, "task"], "t2"))
    with pytest.raises(StagedDraftError) as info:
        staged(cli)
    error = info.value
    assert error.stage == "tester" and error.outcome is Outcome.COMPLETED
    assert error.problems == ["check c01 belongs to t2 but S1.1 is delivered by t1"]
    assert list(error.paid) == ["system_designer", "tester"]
    assert error.paid["system_designer"] == USAGE and error.paid["tester"] == USAGE
    assert str(error).startswith("tester: check c01 belongs to t2")


def test_a_tester_call_that_fails_carries_both_usages_and_its_outcome(cli):
    cli.designer(DESIGN)
    cli.tester(
        json.dumps(
            RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"}
        )
    )
    with pytest.raises(StagedDraftError) as info:
        staged(cli)
    assert info.value.stage == "tester" and info.value.outcome is Outcome.LOGIN
    assert set(info.value.paid) == {"system_designer", "tester"}


def test_a_check_that_passes_on_an_empty_workspace_fails_after_both_calls_were_paid(cli):
    cli.designer(DESIGN)
    cli.tester(edited_tests(["checks", 2, "code"], "def test_always():\n    assert True\n"))
    with pytest.raises(StagedDraftError) as info:
        staged(cli)
    error = info.value
    assert error.stage == "assembly" and error.outcome is Outcome.COMPLETED
    assert error.problems == ["check c03 passes on an empty workspace"]
    assert error.paid == {"system_designer": USAGE, "tester": USAGE}


@pytest.mark.parametrize(
    ("kwargs", "budget", "idea"),
    [
        ({}, 500_000, ""),
        ({}, 500_000, "  \n"),
        ({}, 500_000, "-rf"),
        ({}, 0, IDEA),
        ({}, -5, IDEA),
        ({}, 1.5, IDEA),
        ({}, True, IDEA),
        ({"max_tasks": 0}, 500_000, IDEA),
    ],
)
def test_bad_arguments_are_refused_before_any_call_is_paid(cli, kwargs, budget, idea):
    with pytest.raises(ValueError):
        draft_staged(
            idea,
            budget,
            cli.checks_dir,
            stories=STORIES,
            max_tasks=kwargs.get("max_tasks", 2),
            env=cli.env,
            model="haiku",
            executable=cli.executable,
        )
    assert cli.calls == []


def test_assembling_needs_no_call_and_strips_the_idea(cli):
    plan, _ = checks_of(cli, TESTS)
    calls = len(cli.calls)
    sheet = assemble_term_sheet(f"\n{IDEA}\n", 300_000, STORIES, design_obj(), plan, cli.checks_dir)
    assert sheet.idea == IDEA and sheet.rounds == (Round(1, 300_000, 3),)
    assert sheet.checks == plan.checks and len(cli.calls) == calls


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda plan: replace(plan, untestable=()), "criterion S2.2 has no check"),
        (
            lambda plan: replace(plan, checks=plan.checks[:2]),
            "task t2 has no check, so its progress cannot be measured",
        ),
        (
            lambda plan: replace(
                plan, checks=(replace(plan.checks[0], task="t2"), *plan.checks[1:])
            ),
            "check c01 belongs to t2 but S1.1 is delivered by t1",
        ),
    ],
    ids=["uncovered", "task-without-check", "wrong-task"],
)
def test_a_plan_that_does_not_fit_the_stories_and_design_is_refused(cli, mutate, expected):
    plan, _ = checks_of(cli, TESTS)
    with pytest.raises(ValueError, match="does not fit") as info:
        assemble_term_sheet(IDEA, 300_000, STORIES, design_obj(), mutate(plan), cli.checks_dir)
    assert expected in str(info.value)


def test_a_plan_whose_files_are_not_in_the_directory_is_refused(cli, tmp_path):
    plan, _ = checks_of(cli, TESTS)
    with pytest.raises(ValueError, match="check c01 file test_c01.py does not exist"):
        assemble_term_sheet(IDEA, 300_000, STORIES, design_obj(), plan, tmp_path / "elsewhere")


def test_more_rounds_are_planned_by_story_priority_and_the_sheet_still_validates(cli):
    cli.designer(DESIGN)
    cli.tester(TESTS)
    draft = staged(cli, n_rounds=2)
    # S1 is `must` (c01, c02), S2 is `should` (c03): unlock at 2 checks, then at all 3
    assert draft.sheet.rounds == (Round(1, 298_334, 2), Round(2, 201_666, 3))
    validate(draft.sheet, cli.checks_dir)


def test_a_round_count_below_one_is_refused_before_any_call(cli):
    with pytest.raises(ValueError, match="n_rounds"):
        staged(cli, n_rounds=0)
    assert cli.calls == []
