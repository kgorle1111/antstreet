"""The `single-review` arm: the single agent, then its own session resumed once for a review."""

# ruff: noqa: F811  (the `bench` fixture is imported from test_bench_run, then used by name)

import json
import re

import pytest
from docs_support import ROOT
from test_bench_run import REFERENCE, SHALLOW, TASK, bench  # noqa: F401

from boss.bench.results import ARMS, cell_dir, load_results
from boss.bench.run import (
    BUILD_SHARE,
    DEFAULT_ARMS,
    SELF_REVIEW_PROMPT,
    SLICE_SHARE,
    main,
    slice_caps,
)
from boss.boss import load_prompt
from boss.ledger import EventType, read_events


def flag(argv, name):
    return argv[argv.index(name) + 1]


def test_it_builds_then_resumes_the_same_session_once_to_review(bench):
    result = bench("single-review")
    build, review = bench.calls()
    assert flag(build, "--session-id") == flag(review, "--resume")
    assert "--resume" not in build and "--session-id" not in review
    assert TASK.idea in build[-1]
    assert review[-1] == load_prompt(SELF_REVIEW_PROMPT).strip()
    assert TASK.idea not in review[-1]
    for name in ("--model", "--tools", "--allowedTools", "--permission-mode"):
        assert flag(build, name) == flag(review, name), name
    assert flag(build, "--append-system-prompt") == flag(review, "--append-system-prompt")
    assert (result.arm, result.passed, result.cost_micros) == ("single-review", True, 12_000)
    assert result.boss_micros == 0 and (result.visible_passed, result.visible_total) == (None, None)


def test_the_two_caps_together_never_exceed_the_single_arms_share_of_the_budget(bench):
    bench("single-review")
    build, review = (float(flag(c, "--max-budget-usd")) for c in bench.calls())
    assert (build, review) == (0.24, 0.08)
    assert build + review <= 0.40 * SLICE_SHARE + 1e-9
    bench("single", rep=2)
    single = float(flag(bench.calls()[-1], "--max-budget-usd"))
    assert single == pytest.approx(build + review)  # the same total as the single arm


@pytest.mark.parametrize("budget", [3, 7, 100, 399_999, 400_000, 1_000_003])
def test_slice_caps_are_whole_micros_that_sum_to_the_single_arms_cap(budget):
    build, review = slice_caps(budget, review=True)
    assert build >= 1 and review >= 1
    assert build + review == max(1, int(budget * SLICE_SHARE))
    assert abs(build - BUILD_SHARE * (build + review)) < 1
    assert slice_caps(budget, review=False) == [build + review]


def test_a_budget_too_small_to_split_is_refused():
    with pytest.raises(ValueError, match="too small to split"):
        slice_caps(1, review=True)


def test_hidden_checks_and_reference_are_in_neither_prompt_or_workspace(bench):
    bench("single-review", product=SHALLOW)
    prompts = json.dumps(bench.calls())
    for path in sorted(TASK.hidden_dir.glob("test_*.py")):
        assert path.read_text().strip() not in prompts and path.name not in prompts
    assert "hidden_checks" not in prompts and "reference" not in prompts
    for mutant in TASK.mutants():
        assert mutant.name not in prompts
    cell = cell_dir(bench.results, "slugify", "single-review", 1)
    assert {p.name for p in (cell / "workspace").rglob("*") if p.is_file()} == {"slugify.py"}


def test_the_review_prompt_does_not_mention_what_the_work_is_judged_by():
    text = load_prompt(SELF_REVIEW_PROMPT)
    assert not re.search(
        r"test|check|grad|score|bench|hidden|arm\b|compar|evaluat|pass|fail", text, re.I
    )
    assert not text.startswith("-") and text.strip()


def test_it_is_graded_exactly_like_single(bench):
    reviewed = bench("single-review", product=SHALLOW)
    single = bench("single", product=SHALLOW)
    assert reviewed.hidden == single.hidden and not reviewed.passed
    assert reviewed.failure_class == single.failure_class == "unlabelled"
    assert reviewed.firm_args == "" and reviewed.wrong_checks is None


def test_the_ledger_has_two_slices_of_one_session_and_the_second_is_the_outcome(bench):
    bench("single-review")
    events = read_events(cell_dir(bench.results, "slugify", "single-review", 1) / "ledger.jsonl")
    starts = [e for e in events if e.event is EventType.SLICE_START]
    ends = [e for e in events if e.event is EventType.SLICE_END]
    assert [e.data["slice"] for e in starts] == [1, 2] == [e.data["slice"] for e in ends]
    assert starts[0].data["session"] == starts[1].data["session"]
    assert [e.data["cap_micros"] for e in starts] == [240_000, 80_000]
    assert sum(e.cost_micros or 0 for e in ends) == 12_000


def test_a_build_that_did_not_end_normally_is_not_reviewed(bench):
    (bench.home / "login_broken").write_text("")
    result = bench("single-review")
    assert len(bench.calls()) == 1
    assert (result.outcome, result.failure_class) == ("login", "infrastructure")


def test_single_does_not_review(bench):
    bench("single")
    assert len(bench.calls()) == 1


def test_it_is_asked_for_by_name_and_not_run_by_default(bench, capsys):
    (bench.home / "product.py").write_text(REFERENCE)
    argv = ["--tasks", str(TASK.root.parent), "--out", str(bench.results), "--budget", "0.40"]
    argv += ["--only", "slugify"]
    assert main([*argv, "--dry-run"], environ=bench.environ) == 0
    listed = capsys.readouterr().out
    assert "single-review" not in listed and "firm" in listed
    assert main([*argv, "--arms", "single-review", "--reps", "2"], environ=bench.environ) == 0
    results = load_results(bench.results)
    assert [(r.arm, r.rep, r.passed) for r in results] == [
        ("single-review", 1, True),
        ("single-review", 2, True),
    ]


def test_the_method_note_states_the_split_and_the_arm_is_listed_everywhere_arms_are():
    method = " ".join((ROOT / "bench" / "METHOD.md").read_text(encoding="utf-8").split())
    share, build = int(SLICE_SHARE * 100), int(BUILD_SHARE * 100)
    assert (
        f"{share}% of the cell budget, split {build}% to the build and {100 - build}% to" in method
    )
    assert "`src/boss/prompts/self_review_v1.md`" in method
    assert "single-review" in ARMS and "single-review" not in DEFAULT_ARMS
    assert "`single-review`" in (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
