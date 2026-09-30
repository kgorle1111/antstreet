"""The draft evaluation's staged mode: product manager, system designer and tester in place of
the boss's one call, scored the same way. A fake `claude` plays all three; no model calls."""

import json
import sys
from pathlib import Path

import pytest

from boss.bench.drafts import FAILED, INVALID, SCORED, STAGED, main, run_draft, settings_for
from boss.bench.tasks import load_task, load_tasks, task_set_hash
from boss.roles.base import system_prompt
from boss.roles.engineering import SYSTEM_DESIGNER, TESTER
from boss.roles.product import PRODUCT_MANAGER

TASKS = Path(__file__).parent.parent / "bench" / "tasks"
TASK = load_task(TASKS / "slugify")
LOWER = "from slugify import slugify\n\ndef test_lower():\n    assert slugify('ABC') == 'abc'\n"
ZERO = (
    "import pytest\nfrom slugify import slugify\n\ndef test_zero():\n"
    "    with pytest.raises(ValueError):\n        slugify('a', 0)\n"
)
STORIES = {
    "stories": [
        {
            "id": "S1",
            "as_a": "developer",
            "i_want": "a slug from a title",
            "so_that": "I can build URLs",
            "priority": "must",
            "criteria": [
                {
                    "id": "S1.1",
                    "given": "upper-case text",
                    "when": "slugify is called",
                    "then": "the slug is lower case",
                    "source": "Everything is lowercased.",
                },
                {
                    "id": "S1.2",
                    "given": "a max_length of 0",
                    "when": "slugify is called",
                    "then": "ValueError is raised",
                    "source": "A `max_length` below 1 raises `ValueError`.",
                },
            ],
        }
    ]
}
DESIGN = {
    "tasks": [
        {
            "id": "t1",
            "brief": "Create slugify.py.",
            "paths": ["slugify.py"],
            "stories": ["S1"],
            "interfaces": ["slugify(text: str, max_length: int | None = None) -> str"],
        }
    ]
}
CHECKS = {
    "checks": [
        {"criteria": ["S1.1"], "task": "t1", "description": "lower case", "code": LOWER},
        {"criteria": ["S1.2"], "task": "t1", "description": "rejects zero", "code": ZERO},
    ],
    "untestable": [],
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "modelUsage": {"m": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 1}},
}
# The fake tells the three roles apart by the exact system prompt it is given.
FAKE = f"""#!{sys.executable}
import json, os, sys
home, argv = os.environ["HOME"], sys.argv[1:]
answers = json.load(open(os.path.join(home, "answers.json")))
role = answers["roles"][argv[argv.index("--system-prompt") + 1]]
with open(os.path.join(home, "calls.log"), "a") as log:
    log.write(role + "\\n")
answer = answers[role]
base = {RESULT!r}
if answer == "login":
    print(json.dumps(base | {{"is_error": True, "api_error_status": 401,
                             "terminal_reason": "api_error", "total_cost_usd": 0}}))
else:
    print(json.dumps(base | {{"total_cost_usd": answers["cost"][role],
                             "structured_output": answer}}))
"""


@pytest.fixture
def staged(tmp_path):
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
    roles = {system_prompt(spec): spec.name for spec in (PRODUCT_MANAGER, SYSTEM_DESIGNER, TESTER)}

    def run(**over):
        answers = {
            "roles": roles,
            "product_manager": STORIES,
            "system_designer": DESIGN,
            "tester": CHECKS,
            "cost": {"product_manager": 0.01, "system_designer": 0.02, "tester": 0.04},
        } | over
        (tmp_path / "answers.json").write_text(json.dumps(answers))
        return run_draft(
            TASK,
            1,
            tmp_path / f"out{len(list(tmp_path.glob('out*')))}",
            environ=environ,
            set_hash=task_set_hash(load_tasks(TASKS)),
            settings=settings_for(STAGED, "haiku", None),
        )

    run.calls = lambda: (tmp_path / "calls.log").read_text().split()
    run.environ = environ
    run.home = tmp_path
    return run


def test_a_staged_draft_is_three_calls_scored_like_any_draft(staged):
    cell = staged()
    assert staged.calls() == ["product_manager", "system_designer", "tester"]
    assert cell.status == SCORED and cell.prompt == STAGED
    assert cell.cost_micros == 10_000 + 20_000 + 40_000  # all three calls, not only the last
    assert (cell.tokens_in, cell.tokens_out, cell.tokens_cached) == (30, 15, 3)
    assert cell.score.checks == 2 and cell.score.wrong == ()
    assert 0 < len(cell.score.killed) <= cell.score.mutants


def test_stories_that_fail_their_gate_are_an_invalid_draft_that_still_cost_one_call(staged):
    ungrounded = json.loads(json.dumps(STORIES))
    ungrounded["stories"][0]["criteria"][0]["source"] = "Emoji are removed from the slug."
    cell = staged(product_manager=ungrounded)
    assert staged.calls() == ["product_manager"]  # nothing is designed from rejected stories
    assert cell.status == INVALID and cell.score is None and cell.cost_micros == 10_000
    assert "not a fragment of the idea" in cell.detail


def test_checks_that_leave_a_criterion_uncovered_are_invalid_and_every_call_is_counted(staged):
    uncovered = {"checks": CHECKS["checks"][:1], "untestable": []}
    cell = staged(tester=uncovered)
    assert staged.calls() == ["product_manager", "system_designer", "tester"]
    assert cell.status == INVALID and cell.cost_micros == 70_000
    assert cell.detail.startswith("tester: ") and "S1.2" in cell.detail


def test_a_call_that_fails_is_a_failed_draft_not_an_invalid_one(staged):
    cell = staged(system_designer="login")
    assert staged.calls() == ["product_manager", "system_designer"]
    assert cell.status == FAILED and cell.outcome == "login"
    assert cell.cost_micros == 10_000  # the stories were paid for; the failed call cost nothing


def test_the_staged_settings_change_when_any_of_the_three_prompts_or_skills_change(monkeypatch):
    before = settings_for(STAGED, "haiku", None)
    assert before.prompt == STAGED and len(before.prompt_sha) == 12
    import boss.bench.drafts as drafts

    monkeypatch.setattr(drafts, "system_prompt", lambda spec: f"edited {spec.name}")
    assert settings_for(STAGED, "haiku", None).prompt_sha != before.prompt_sha


def test_the_command_line_runs_a_staged_draft_and_prints_its_cost_ceiling(staged, capsys):
    staged()  # writes answers.json
    out = staged.home / "cli-out"
    argv = ["--tasks", str(TASKS), "--out", str(out), "--only", "slugify", "--prompt", STAGED]
    assert main([*argv, "--dry-run"], environ=staged.environ) == 0
    dry = capsys.readouterr().out
    assert "1 drafts, 1 to make, up to $0.7 at the per-draft cap (not measured yet)" in dry
    assert not out.exists()
    assert main(argv, environ=staged.environ) == 0
    table = capsys.readouterr().out
    assert "slugify" in table and (out / "slugify" / "rep1" / "draft.json").is_file()


def test_one_call_of_unknown_cost_makes_the_drafts_cost_unknown_never_a_smaller_number():
    from boss.bench.drafts import _sum
    from boss.stream import Usage

    total = _sum([Usage(10_000, 1, 2, 3), Usage(None, 4, 5, 6), Usage(7_000, 1, 1, 1)])
    assert total == Usage(None, 6, 8, 10)
    assert _sum([Usage(10_000, 1, 2, 3), Usage(0, 0, 0, 0)]) == Usage(10_000, 1, 2, 3)
    assert _sum([]) == Usage(0, 0, 0, 0)
