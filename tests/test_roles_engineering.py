"""The engineering roles: the system designer's gate, the tester's gate, the coverage matrix and
the staged pipeline. No model calls: a fake `claude` answers the designer and the tester
differently."""

import copy
import json
import sys

import pytest

from boss.errors import Outcome
from boss.roles import registry
from boss.roles.base import RoleError, RoleOutputError, system_prompt
from boss.roles.engineering import (
    SYSTEM_DESIGNER,
    Design,
    DesignTask,
    design_schema,
    design_tasks,
    stories_text,
)
from boss.roles.stories import parse_stories, story_problems
from boss.stream import Usage

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
role = "designer" if "system designer" in system else "tester"
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


def edited(path, value):
    data = copy.deepcopy(DESIGN)
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


def test_every_problem_is_reported_at_once(cli):
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
