"""`draft_term_sheet(prompt_name=...)`: choosing another system prompt, to compare prompts."""

import json
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT_LINE

from boss.boss import MULTI_TASK_PROMPT, TERM_SHEET_PROMPT, draft_term_sheet, load_prompt

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "json_boss_schema_call_2.1.285.json").read_text()
)
CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
FAKE_CLI = f"""#!{sys.executable}
import json, os, sys
open(os.environ["HOME"] + "/argv.json", "w").write(json.dumps(sys.argv))
print({BOSS_INIT_LINE!r})
print({json.dumps(RECORDED | {"structured_output": DRAFT})!r})
"""


@pytest.fixture
def draft(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)

    def run(**kwargs):
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
        return draft_term_sheet(
            "Reverse a string.",
            500_000,
            tmp_path / "checks",
            env=env,
            executable=str(cli),
            **kwargs,
        )

    def system_prompt() -> str:
        argv = json.loads((tmp_path / "argv.json").read_text())
        return argv[argv.index("--system-prompt") + 1]

    run.system_prompt = system_prompt
    run.ran = lambda: (tmp_path / "argv.json").exists()
    return run


def test_without_a_name_the_current_prompts_are_used(draft):
    draft()
    assert draft.system_prompt() == load_prompt(TERM_SHEET_PROMPT)
    draft(max_tasks=2)
    assert draft.system_prompt() == load_prompt(MULTI_TASK_PROMPT)


def test_a_named_prompt_replaces_the_system_prompt_whatever_the_task_limit(draft):
    draft(prompt_name="solo_v2.md")
    assert draft.system_prompt() == load_prompt("solo_v2.md") != load_prompt(TERM_SHEET_PROMPT)
    draft(prompt_name="solo_v2.md", max_tasks=3)
    assert draft.system_prompt() == load_prompt("solo_v2.md")


@pytest.mark.parametrize(
    "name",
    [
        "../term_sheet_v1.md",
        "sub/x.md",
        "/etc/passwd.md",
        "term_sheet_v1",
        "",
        ".md",
        " a.md",
        "a.md\n",
    ],
)
def test_a_prompt_name_must_be_a_plain_markdown_file_name_and_nothing_runs_otherwise(draft, name):
    with pytest.raises(ValueError, match="prompt name"):
        draft(prompt_name=name)
    assert not draft.ran()


def test_a_prompt_that_does_not_exist_is_an_error_before_any_call(draft):
    with pytest.raises(FileNotFoundError):
        draft(prompt_name="no_such_prompt.md")
    assert not draft.ran()


def test_load_prompt_itself_refuses_a_name_that_could_leave_the_prompts_folder():
    assert load_prompt("solo_v2.md")
    with pytest.raises(ValueError, match="prompt name"):
        load_prompt("../prompts/solo_v2.md")
