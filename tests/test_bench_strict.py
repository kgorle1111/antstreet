"""Opt-in strict task validation: flaky reference, check time budget, mutant count, timeout kills.

These run the real gate on tiny tmp_path tasks (the native task format), not on mocks.
"""

import json
from pathlib import Path

import pytest

from antstreet.bench import tasks as bench_tasks
from antstreet.bench import validate as bench_validate
from antstreet.bench.tasks import MIN_HIDDEN_CHECKS, TaskError, load_task, validate_task

pytestmark = pytest.mark.slow  # every test here runs the real gate: seconds each

CALLS_F = "from demo import f\n\ndef test_x():\n    assert f() == 1\n"


def make_task(
    root: Path,
    *,
    mutants: int = 3,
    extra_check: str | None = None,
    reference: str = "def f():\n    return 1\n",
    mutant_source: str | None = None,
) -> Path:
    """A task of MIN_HIDDEN_CHECKS plain checks (+ `extra_check`) and `mutants` wrong `f()`s."""
    folder = root / "demo"
    meta = {"id": "demo", "title": "Demo", "difficulty": "easy"}
    (folder / "hidden_checks").mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps(meta))
    (folder / "idea.md").write_text("Create demo.py with f().")
    for n in range(MIN_HIDDEN_CHECKS):
        (folder / "hidden_checks" / f"test_c{n}.py").write_text(CALLS_F)
    if extra_check is not None:
        (folder / "hidden_checks" / "test_extra.py").write_text(extra_check)
    (folder / "reference").mkdir()
    (folder / "reference" / "demo.py").write_text(reference)
    for n in range(mutants):
        (folder / "mutants" / f"wrong_{n}").mkdir(parents=True)
        source = mutant_source or f"def f():\n    return {n + 2}\n"
        (folder / "mutants" / f"wrong_{n}" / "demo.py").write_text(source)
    return folder


def problems(folder: Path, **options) -> list[str]:
    try:
        validate_task(load_task(folder), **options)
    except TaskError as exc:
        return exc.problems
    return []


# A check that is right but slow: asserts first so wrong solutions fail fast, then sleeps.
SLOW_CHECK = (
    "import time\nfrom demo import f\n\n"
    "def test_slow():\n    assert f() == 1\n    time.sleep(1.5)\n"
)


def test_slow_check_is_rejected_under_a_budget_and_accepted_without(tmp_path):
    folder = make_task(tmp_path, extra_check=SLOW_CHECK)
    assert problems(folder) == []
    # On a loaded machine the plain checks can be over 1 s too, so look for the slow one by name.
    found = [p for p in problems(folder, check_budget_s=1.0) if "check extra took" in p]
    assert len(found) == 1
    assert "over the 1s budget" in found[0] and "compare whole structures" in found[0]
    assert problems(folder, check_budget_s=60.0) == []  # the same check is fine under a big budget


def test_a_mutant_killed_only_by_a_timeout_is_reported_when_timeouts_do_not_kill(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        bench_tasks, "MUTANT_TIMEOUT_S", 4.0
    )  # short, but above a loaded machine's pytest start-up
    only_check_that_calls_f = CALLS_F
    folder = make_task(tmp_path, extra_check=only_check_that_calls_f, mutants=0)
    for n in range(2):  # two ordinary wrong solutions, killed by a failing assertion
        (folder / "mutants" / f"wrong_{n}").mkdir(parents=True)
        (folder / "mutants" / f"wrong_{n}" / "demo.py").write_text(
            f"def f():\n    return {n + 2}\n"
        )
    # The hanging mutant: only test_hang calls f, so only it can be killed (here, by timeout).
    for path in (folder / "hidden_checks").glob("test_c*.py"):
        path.write_text("import demo\n\ndef test_x():\n    assert callable(demo.f)\n")
    (folder / "hidden_checks" / "test_extra.py").rename(folder / "hidden_checks" / "test_hang.py")
    (folder / "mutants" / "hangs").mkdir(parents=True)
    (folder / "mutants" / "hangs" / "demo.py").write_text(
        "def f():\n    while True:\n        pass\n"
    )
    assert problems(folder) == []  # default: a timeout kills
    found = problems(folder, timeout_kills=False)
    assert len(found) == 1
    assert "mutant hangs" in found[0] and "check hang" in found[0] and "timeout" in found[0]


def test_a_flaky_reference_is_caught_by_repeated_runs(tmp_path, monkeypatch):
    folder = make_task(tmp_path)
    reference = folder / "reference"
    real_gate = bench_tasks.run_gate
    seen = {"reference_runs": 0}

    def flaky_gate(workspace, *args, **kwargs):
        results = real_gate(workspace, *args, **kwargs)
        if Path(workspace) == reference:  # after the 1st reference run, the reference goes wrong
            seen["reference_runs"] += 1
            (reference / "demo.py").write_text("def f():\n    return 2\n")
        return results

    monkeypatch.setattr(bench_tasks, "run_gate", flaky_gate)
    assert problems(folder) == []  # a single run only ever sees the passing one
    (reference / "demo.py").write_text("def f():\n    return 1\n")
    found = problems(folder, reference_runs=3)
    assert seen["reference_runs"] == 1 + 3
    assert found and all("reference run" in p and "of 3" in p for p in found)
    assert any("reference run 2 of 3" in p and "flaky" in p for p in found)
    assert not any("reference run 1 of 3" in p for p in found)


def test_min_mutants_is_enforced_before_any_gate_run(tmp_path):
    folder = make_task(tmp_path, mutants=3)
    found = problems(folder, min_mutants=8)
    assert found == [
        "has 3 mutants, strict validation needs at least 8; "
        "add wrong solutions under mutants/, each breaking one rule the checks should catch"
    ]


@pytest.mark.parametrize(
    "options",
    [
        {"reference_runs": 0},
        {"reference_runs": 1.5},
        {"reference_runs": True},
        {"check_budget_s": 0},
        {"check_budget_s": -1.0},
        {"check_budget_s": float("inf")},
        {"check_budget_s": float("nan")},
        {"check_budget_s": "1"},
        {"min_mutants": -1},
        {"min_mutants": 2.0},
    ],
)
def test_option_values_are_validated(tmp_path, options):
    folder = make_task(tmp_path)
    with pytest.raises(ValueError, match="must be"):
        validate_task(load_task(folder), **options)


def test_the_options_are_keyword_only(tmp_path):
    folder = make_task(tmp_path)
    with pytest.raises(TypeError):
        validate_task(load_task(folder), 3)  # type: ignore[misc]


def test_cli_exit_codes_and_messages(tmp_path, capsys):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    make_task(tasks)
    assert bench_validate.main([str(tasks)]) == 0
    out = capsys.readouterr().out
    assert "ok   demo" in out and "slowest check c" in out and "1 of 1 tasks passed" in out
    assert bench_validate.main([str(tasks), "--strict"]) == 1  # only 3 mutants
    out = capsys.readouterr().out
    assert (
        "FAIL demo" in out and "needs at least 8" in out and "0 of 1 tasks passed (strict)" in out
    )
    assert bench_validate.main([str(tmp_path / "missing")]) == 2
    assert "is not a folder" in capsys.readouterr().err
    empty = tmp_path / "empty"
    empty.mkdir()
    assert bench_validate.main([str(empty)]) == 2
    assert "no tasks" in capsys.readouterr().err


def test_cli_strict_passes_a_task_that_meets_every_bound(tmp_path, capsys, monkeypatch):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    make_task(tasks, mutants=8)
    # The 1 s budget is wall time and fails on a busy machine; the other bounds are what is tested.
    monkeypatch.setitem(bench_validate.STRICT, "check_budget_s", 60.0)
    assert bench_validate.main([str(tasks), "--strict"]) == 0
    assert "1 of 1 tasks passed (strict)" in capsys.readouterr().out


def test_cli_reports_a_malformed_task_and_still_validates_the_others(tmp_path, capsys):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    make_task(tasks)
    (tasks / "broken").mkdir()
    (tasks / "broken" / "meta.json").write_text("{not json")
    assert bench_validate.main([str(tasks)]) == 1
    out = capsys.readouterr().out
    assert "FAIL broken" in out and "ok   demo" in out and "1 of 2 tasks passed" in out


def test_cli_keeps_its_summary_when_the_timing_run_hits_a_gate_error(tmp_path, capsys, monkeypatch):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    make_task(tasks)

    def no_gate(*args: object, **kwargs: object) -> None:
        raise bench_validate.GateError("sandbox unavailable")

    monkeypatch.setattr(bench_validate, "run_gate", no_gate)
    assert bench_validate.main([str(tasks)]) == 0
    out = capsys.readouterr().out
    assert "slowest check n/a (sandbox unavailable)" in out and "1 of 1 tasks passed" in out
