"""The benchmark's firm arm with held-out checks: `held_out` reaches `boss fund`, each cell records
how many held-out checks the product passed, and results written before the fields load. The CLI's
own run is replaced by a stub that writes a run folder, so this needs no fake `claude`."""

import json
import shutil
from pathlib import Path

import pytest

from boss.bench import run as bench_run
from boss.bench.results import CellResult, cell_dir, load_results
from boss.bench.run import _held_out_counts, main, run_cell
from boss.bench.tasks import load_task
from boss.ledger import Event, EventType, LedgerWriter

TASK = load_task(Path(__file__).parent.parent / "bench" / "tasks" / "slugify")
HASHES = {"manifest.json": "0" * 64} | {f"test_h0{n}.py": str(n) * 64 for n in (1, 2, 3)}


def ev(kind, actor="boss", round=1, **data) -> Event:
    return Event(run="r1", round=round, actor=actor, event=kind, data=data)


def firm_ledger(*, statuses=("passed", "passed", "failed"), written=True, requested=3):
    events = [
        ev(EventType.STARTED, round=0, config={"held_out": requested}),
        ev(EventType.APPROVED, "investor", round=0, hashes={"term_sheet": "a"}, **(
            {"held_out_hashes": HASHES} if written else {}
        )),
        ev(EventType.SLICE_END, "worker:w1", slice=1, task="t1", outcome="completed", status={}),
        ev(EventType.ROUND_CLOSED, passed=1, total=1, unlocked=True),
    ]  # fmt: skip
    for n, status in enumerate(statuses, start=1):
        events.append(ev(EventType.CHECK_RESULT, "gate", check=f"h0{n}", status=status,
                         detail="", scope="held_out"))  # fmt: skip
    return events


@pytest.fixture
def stub(tmp_path, monkeypatch):
    """Replace `boss fund` with a stub that records its argv and writes the run folder the firm
    arm reads: a ledger from `stub.events` and the reference solution as product/."""
    calls = []
    stub = type("Stub", (), {})()
    stub.events, stub.calls = firm_ledger(), calls

    def fake_main(argv, *, ask, say, environ):
        calls.append(list(argv))
        out = Path(argv[argv.index("--dir") + 1])
        run_dir = out / ".boss" / "runs" / "r1"
        (run_dir / "checks").mkdir(parents=True)
        shutil.copytree(TASK.reference_dir, run_dir / "product")
        with LedgerWriter(run_dir / "ledger.jsonl") as ledger:
            for event in stub.events:
                ledger.append(event)
        return 0

    monkeypatch.setattr(bench_run.cli, "main", fake_main)
    stub.results = tmp_path / "results"
    stub.cell = lambda arm="firm", **kw: run_cell(
        TASK, arm, 1, stub.results, environ={"PATH": "/usr/bin:/bin"}, set_hash="abc",
        budget_micros=400_000, **kw,
    )  # fmt: skip
    return stub


def test_held_out_reaches_the_firm_arms_boss_fund_and_is_recorded(stub):
    result = stub.cell(held_out=3, firm_args=["--slice", "0.05"])
    [argv] = stub.calls
    assert argv[argv.index("--slice") :][:4] == ["--slice", "0.05", "--held-out", "3"]
    assert result.firm_args == "--slice 0.05 --held-out 3"
    assert (result.held_out_passed, result.held_out_total) == (2, 3)
    assert result.passed  # the reference passes every hidden check; the held-out count is separate
    saved = CellResult.load(cell_dir(stub.results, "slugify", "firm", 1) / "result.json")
    assert saved == result


def test_a_cell_that_asks_for_none_passes_no_option_and_records_no_count(stub):
    stub.events = firm_ledger(statuses=(), written=False, requested=0)
    result = stub.cell()
    [argv] = stub.calls
    assert "--held-out" not in argv and result.firm_args == ""
    assert (result.held_out_passed, result.held_out_total) == (None, None)


def test_the_single_arm_is_untouched_by_held_out(stub, monkeypatch):
    def single(task, out, environ, model, budget_micros):
        workspace = out / "workspace"
        shutil.copytree(TASK.reference_dir, workspace)
        (out / "ledger.jsonl").write_text("")
        return workspace, [ev(EventType.SLICE_END, "worker:solo", outcome="completed")]

    monkeypatch.setattr(bench_run, "_run_single", single)
    result = stub.cell("single", held_out=3)
    assert stub.calls == []
    assert (result.firm_args, result.held_out_passed, result.held_out_total) == ("", None, None)


@pytest.mark.parametrize("bad", [-1, 9, True, 2.0, "3", None])
def test_a_bad_count_is_refused_before_anything_runs(stub, bad):
    with pytest.raises(ValueError, match="held_out must be a whole number from 0 to 8"):
        stub.cell(held_out=bad)
    assert stub.calls == [] and not stub.results.exists()


# --- the counts -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statuses", "written", "expected"),
    [
        (("passed", "passed", "passed"), True, (3, 3)),
        (("failed", "timeout", "failed"), True, (0, 3)),
        (("passed",), True, (1, 3)),  # the run ended before it graded the rest: not passed
        ((), True, (0, 3)),  # approved, never graded
        (("passed", "failed"), False, (1, 2)),  # graded with no approval recorded
        ((), False, (None, None)),  # the examiner kept nothing, or was never asked
    ],
)
def test_counts_are_passed_over_approved_and_an_ungraded_check_is_not_passed(
    statuses, written, expected
):
    assert _held_out_counts(firm_ledger(statuses=statuses, written=written)) == expected


def test_no_events_means_no_count():
    assert _held_out_counts([]) == (None, None)


def test_a_firm_run_whose_examiner_failed_records_no_count(stub):
    stub.events = [
        *firm_ledger(statuses=(), written=False)[:1],
        ev(EventType.ROLE_CALL, "role:examiner", outcome="timeout", kept=0, problems=["x"]),
        *firm_ledger(statuses=(), written=False)[1:],
    ]
    result = stub.cell(held_out=3)
    assert (result.held_out_passed, result.held_out_total) == (None, None)
    assert result.firm_args == "--held-out 3"  # what was asked is still on the record


# --- the command line -------------------------------------------------------------------------


def test_the_command_line_option_is_passed_to_every_cell_and_shown(stub, capsys):
    tasks = str(TASK.root.parent)
    argv = ["--tasks", tasks, "--out", str(stub.results), "--budget", "0.40", "--only", "slugify"]
    assert main([*argv, "--arms", "firm", "--held-out", "3"], environ={"PATH": "/x"}) == 0
    [call] = stub.calls
    assert call[-2:] == ["--held-out", "3"]
    assert "2/3 held-out" in capsys.readouterr().out
    [result] = load_results(stub.results)
    assert (result.held_out_passed, result.held_out_total) == (2, 3)


@pytest.mark.parametrize("bad", ["9", "-1", "x"])
def test_the_command_line_option_refuses_what_is_not_zero_to_eight(tmp_path, bad):
    argv = ["--out", str(tmp_path), "--budget", "0.40", "--held-out", bad]
    with pytest.raises(SystemExit) as raised:
        main(argv, environ={})
    assert raised.value.code == 2


def test_the_default_is_off(stub):
    tasks = str(TASK.root.parent)
    argv = ["--tasks", tasks, "--out", str(stub.results), "--budget", "0.40", "--only", "slugify"]
    stub.events = firm_ledger(statuses=(), written=False, requested=0)
    assert main([*argv, "--arms", "firm"], environ={"PATH": "/x"}) == 0
    assert "--held-out" not in stub.calls[0]


# --- results written before the fields load ---------------------------------------------------


def saved_cell(tmp_path, **extra) -> dict:
    CellResult(
        task="slugify", arm="firm", rep=1, set_hash="abc", model="haiku", budget_micros=1,
        hidden={"h": "passed"}, visible_passed=1, visible_total=1, cost_micros=1, boss_micros=1,
        unknown_cost_events=0, outcome="completed", failure_class=None, duration_s=1.0,
        **extra,
    ).save(tmp_path)  # fmt: skip
    return json.loads((tmp_path / "result.json").read_text())


def test_results_written_before_the_held_out_fields_still_load(tmp_path):
    raw = saved_cell(tmp_path, held_out_passed=1, held_out_total=2)
    del raw["held_out_passed"], raw["held_out_total"]
    (tmp_path / "result.json").write_text(json.dumps(raw))
    old = CellResult.load(tmp_path / "result.json")
    assert (old.held_out_passed, old.held_out_total) == (None, None)


@pytest.mark.parametrize(
    ("passed", "total", "message"),
    [
        ("one", 2, "held_out_passed"),
        (1, True, "held_out_total"),
        (True, 2, "held_out_passed"),
        (1.0, 2, "held_out_passed"),
        (1, None, "recorded together or not at all"),
        (None, 2, "recorded together or not at all"),
        (3, 2, "must be between 0 and held_out_total 2"),
        (-1, 2, "must be between 0 and held_out_total 2"),
    ],
)
def test_held_out_fields_are_type_and_range_checked_on_load(tmp_path, passed, total, message):
    raw = saved_cell(tmp_path, held_out_passed=1, held_out_total=2)
    raw["held_out_passed"], raw["held_out_total"] = passed, total
    (tmp_path / "result.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError, match=message):
        CellResult.load(tmp_path / "result.json")
