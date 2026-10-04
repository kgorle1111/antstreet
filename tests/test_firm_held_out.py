"""Held-out checks in the round loop: graded only on the assembled product, never reaching a worker,
bound to the investor's approval, finished on resume, and ignored by every per-worker decision.
A scripted worker and the real gate; a fake `claude` for the examiner. No model calls."""

import dataclasses
import functools
import json
import re
import sys

import pytest
from boss_init import BOSS_INIT_LINE
from test_firm import BAD, C01, C02, C03, ENV, GOOD, HALF, STARTED, Script, sheet, step

from boss import held_out
from boss.approval import NotApprovedError, content_hashes, review_term_sheet
from boss.firm import FirmConfig, FirmReport, config_data, config_from_data, run_firm
from boss.gate import run_gate
from boss.ledger import Event, EventType, LedgerWriter, read_events, total
from boss.limits import RunLimits
from boss.report import build_report, render_report
from boss.roles.examiner import run_examiner
from boss.rule import FiringPolicy
from boss.rundir import RunPaths
from boss.runner import run_slice
from boss.state import run_state, slice_history
from boss.termsheet import Round

HP = "from rev import reverse\n\ndef test_held_pass():\n    assert reverse('xy') == 'yx'\n"
HF = "from rev import reverse\n\ndef test_held_fail():\n    assert reverse('xy') == 'nope'\n"
HS = "reverse('xy') returns 'yx'"  # a quote of the idea, in the manifest and never in a prompt
IDEA = "Reverse a string. reverse('xy') returns 'yx'."


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


def write_held_out(paths, *codes):
    entries = [
        (held_out.HeldOutCheck(f"h{n:02d}", held_out.file_name(f"h{n:02d}"), HS), code)
        for n, code in enumerate(codes, start=1)
    ]
    held_out.write(paths.held_out, entries)


def run(paths, worker, s=None, *, codes=(), config=None, gate=run_gate, approve=True):
    """Approve the sheet with its held-out folder (written from `codes`) and run the loop."""
    s = s or sheet()
    said = []
    if codes and not paths.held_out.exists():
        write_held_out(paths, *codes)
    with LedgerWriter(paths.ledger) as ledger:
        if approve and not paths.ledger.read_text():
            data = {"hashes": content_hashes(s, paths.checks)}
            if held_out.hashes(paths.held_out):
                data["held_out_hashes"] = held_out.hashes(paths.held_out)
            ledger.append(
                Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
            )
        report = run_firm(
            s, paths, ledger, "r1", env=ENV,
            config=None if config is STARTED else (config or FirmConfig()),
            ask=lambda _: "n", say=said.append, slice_runner=worker, gate=gate,
            sleep=lambda _: None,
        )  # fmt: skip
    return report, said


def events_of(paths, kind):
    return [e for e in read_events(paths.ledger) if e.event is kind]


def held_results(paths):
    return [
        (e.data["check"], e.data["status"])
        for e in events_of(paths, EventType.CHECK_RESULT)
        if e.data.get("scope") == "held_out"
    ]


# --- the verdict ------------------------------------------------------------------------------


def test_held_out_checks_are_graded_on_the_product_and_recorded_with_their_own_scope(paths):
    report, said = run(paths, Script(step(GOOD, "done")), codes=(HP, HF))
    assert held_results(paths) == [("h01", "passed"), ("h02", "failed")]
    assert (report.passed, report.total) == (2, 2)
    assert (report.held_out_passed, report.held_out_total) == (1, 2)
    assert not report.all_passed  # every visible check passed and one held-out check did not
    assert "Held-out checks: 1 of 2 passed on the product; the workers never saw them." in said
    [first, _] = [
        e for e in events_of(paths, EventType.CHECK_RESULT) if e.data.get("scope") == "held_out"
    ]
    assert first.actor == "gate"
    assert set(first.data) == {"check", "status", "detail", "scope", "sandboxed"}
    assert first.data["scope"] == "held_out"


def test_a_run_passes_only_when_every_visible_and_every_held_out_check_passes(paths):
    report, _ = run(paths, Script(step(GOOD, "done")), codes=(HP, HP))
    assert (report.held_out_passed, report.held_out_total) == (2, 2) and report.all_passed


def test_a_run_without_held_out_checks_changes_nothing(paths):
    report, said = run(paths, Script(step(GOOD, "done")))
    assert report == FirmReport(2, 2, None, 0, 0) and report.all_passed
    assert held_results(paths) == []
    assert not any("Held-out" in line for line in said)
    [approval] = events_of(paths, EventType.APPROVED)
    assert "held_out_hashes" not in approval.data


def test_held_out_checks_are_run_on_the_product_folder_and_never_in_a_workers_folder(paths):
    seen = []

    def gate(workspace, checks_dir, checks):
        seen.append((workspace.name, checks_dir.name, [c.id for c in checks]))
        return run_gate(workspace, checks_dir, checks)

    run(paths, Script(step(GOOD, "done")), codes=(HP,), gate=gate)
    assert [s for s in seen if s[1] == "held_out"] == [("product", "held_out", ["h01"])]
    assert all("h01" not in ids for name, _, ids in seen if name != "product")


def test_a_held_out_check_that_the_product_fails_does_not_stop_fire_or_abandon_anyone(paths):
    worker = Script(step(GOOD, "done"))
    report, _ = run(paths, worker, codes=(HF, HF, HF))
    assert len(worker.specs) == 1 and report.stopped is None
    assert not events_of(paths, EventType.FIRED) and not events_of(paths, EventType.ABANDONED)
    assert held_results(paths) == [("h01", "failed"), ("h02", "failed"), ("h03", "failed")]


def test_nothing_built_means_held_out_checks_are_reported_as_not_passed(paths):
    unfunded = dataclasses.replace(sheet(), budget_micros=100_000, rounds=(Round(1, 100_000, 2),))
    report, _ = run(paths, Script(), unfunded, codes=(HP, HP))
    assert events_of(paths, EventType.SLICE_START) == []
    assert (report.held_out_passed, report.held_out_total) == (0, 2)
    assert not report.all_passed and held_results(paths) == []


def test_the_product_gate_is_not_repeated_for_held_out_checks_on_a_finished_run(paths):
    run(paths, Script(step(GOOD, "done")), codes=(HP, HF))
    before = held_results(paths)
    report, _ = run(paths, Script(), config=STARTED)
    assert held_results(paths) == before and (report.held_out_passed, report.held_out_total) == (
        1,
        2,
    )


def test_a_product_over_the_size_limit_leaves_held_out_checks_ungraded_and_says_so(paths):
    worker = Script(step(GOOD, "done"))
    small = FirmConfig(limits=RunLimits(max_workspace_bytes=1))
    report, said = run(paths, worker, codes=(HP,), config=small)
    assert held_results(paths) == []
    assert (report.held_out_passed, report.held_out_total) == (0, 1) and not report.all_passed
    assert any("held-out checks were not run" in line for line in said)


# --- resume -----------------------------------------------------------------------------------


def test_a_held_out_verdict_cut_short_is_finished_on_resume_without_redoing_what_is_done(paths):
    run(paths, Script(step(GOOD, "done")), codes=(HP, HF))
    lines = paths.ledger.read_text().splitlines()
    second = [i for i, line in enumerate(lines) if '"scope": "held_out"' in line][1]
    paths.ledger.write_text("\n".join(lines[:second]) + "\n")  # killed after the first result
    assert held_results(paths) == [("h01", "passed")]
    graded = []

    def gate(workspace, checks_dir, checks):
        graded.append([c.id for c in checks])
        return run_gate(workspace, checks_dir, checks)

    report, _ = run(paths, Script(), config=STARTED, gate=gate)
    assert graded == [["h02"]]  # only the check with no result is run
    assert held_results(paths) == [("h01", "passed"), ("h02", "failed")]
    assert (report.held_out_passed, report.held_out_total) == (1, 2)


def test_a_kill_before_any_held_out_result_grades_all_of_them_on_resume(paths):
    run(paths, Script(step(GOOD, "done")), codes=(HP, HF))
    lines = paths.ledger.read_text().splitlines()
    first = [i for i, line in enumerate(lines) if '"scope": "held_out"' in line][0]
    paths.ledger.write_text("\n".join(lines[:first]) + "\n")
    report, _ = run(paths, Script(), config=STARTED)
    assert held_results(paths) == [("h01", "passed"), ("h02", "failed")]
    assert report.held_out_total == 2


# --- never reaches a worker -------------------------------------------------------------------


class Recording:
    """A scripted worker that records everything a worker could see: its prompts, its environment
    and every file in its folder, before and after the slice."""

    def __init__(self, worker):
        self.worker, self.seen = worker, []

    def __call__(self, spec, workspace, log_path, *, env):
        def files():
            return {
                p.relative_to(workspace).as_posix(): p.read_text(errors="replace")
                for p in workspace.rglob("*")
                if p.is_file()
            }

        self.seen.append(json.dumps([spec.prompt, spec.append_system_prompt, dict(env)]))
        self.seen.append(json.dumps(files()))
        result = self.worker(spec, workspace, log_path, env=env)
        self.seen.append(json.dumps(files()))
        return result


def test_held_out_text_reaches_no_prompt_environment_or_workspace_of_any_worker(paths):
    # A stalled first worker (continuation prompts with gate output, then a firing) and a
    # replacement (reassignment brief, handoff of the first worker's files): every channel.
    bodies = (HP, HF)
    recording = Recording(Script(step(BAD), step(BAD), step(GOOD, "done")))
    report, _ = run(
        paths, recording, codes=bodies, config=FirmConfig(policy=FiringPolicy(stall_slices=2))
    )
    assert events_of(paths, EventType.FIRED) and len(recording.worker.specs) == 3
    everything = "\n".join(recording.seen)
    for body in bodies:
        assert body.strip() not in everything
        assert body.splitlines()[-1].strip() not in everything
    for needle in ("test_h01.py", "test_h02.py", "manifest.json", HS, "held_test"):
        assert needle not in everything, needle
    assert not re.search(r"\bh0[12]\b", everything)
    assert report.held_out_total == 2


INIT = {
    "type": "system",
    "subtype": "init",
    "tools": ["Read", "Write", "Edit", "StructuredOutput"],
    "mcp_servers": [],
    "permissionMode": "dontAsk",
    "claude_code_version": "2.1.285",
    "session_id": "s-1",
}
# A stand-in for the `claude` CLI that records what a real worker process is given: its argv, its
# environment and every file in its folder, then builds the product and reports done.
FAKE_WORKER = f"""#!{sys.executable}
import json, os, sys
home = os.environ["HOME"]
files = {{p: open(p, errors="replace").read() for p in os.listdir(".") if os.path.isfile(p)}}
with open(os.path.join(home, "worker.log"), "a") as log:
    log.write(json.dumps([sys.argv[1:], dict(os.environ), files, os.getcwd()]) + "\\n")
say = lambda e: print(json.dumps(e), flush=True)
say({INIT!r})
open("rev.py", "w").write({GOOD!r})
say({{"type": "result", "subtype": "success", "is_error": False, "terminal_reason": "completed",
     "session_id": "s-1", "total_cost_usd": 0.006,
     "modelUsage": {{"m": {{"inputTokens": 10, "outputTokens": 5}}}},
     "structured_output": {{"status": "done", "reason": "wrote it"}}}})
"""


def test_held_out_text_never_reaches_a_real_worker_processs_command_environment_or_folder(
    paths, tmp_path
):
    # The same channels as above through the real runner and command builder: what the `claude`
    # process is started with, what it inherits, and what its folder holds when it starts.
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_WORKER)
    fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    write_held_out(paths, HP, HF)
    s = sheet()
    with LedgerWriter(paths.ledger) as ledger:
        data = {
            "hashes": content_hashes(s, paths.checks),
            "held_out_hashes": held_out.hashes(paths.held_out),
        }
        ledger.append(
            Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
        report = run_firm(
            s, paths, ledger, "r1", env=env, config=FirmConfig(),
            ask=lambda _: "n", say=lambda _: None,
            slice_runner=functools.partial(run_slice, executable=str(fake)), sleep=lambda _: None,
        )  # fmt: skip
    assert (report.held_out_passed, report.held_out_total) == (1, 2)
    [record] = [json.loads(line) for line in (home / "worker.log").read_text().splitlines()]
    argv, environment, files, cwd = record
    everything = json.dumps(record)
    for body in (HP, HF):
        assert body.strip() not in everything
    for needle in ("test_h01.py", "test_h02.py", "manifest.json", HS, "held_test"):
        assert needle not in everything, needle
    assert str(paths.held_out) not in everything
    assert not re.search(r"\bh0[12]\b", everything)
    assert files == {} and set(environment) >= {"HOME", "PATH"}  # an empty folder to start in
    assert argv[argv.index("--tools") + 1] == "Read,Write,Edit"  # no way to reach another folder


def test_the_held_out_folder_is_outside_every_workspace_and_out_of_the_product(paths):
    run(paths, Script(step(GOOD, "done")), codes=(HP,))
    folder = paths.held_out.resolve()
    assert paths.root.resolve() in folder.parents
    for place in [paths.root / "workspaces", paths.product]:
        assert place.resolve() not in folder.parents and folder != place.resolve()
        assert not any(p.name in {"manifest.json", "test_h01.py"} for p in place.rglob("*"))
    assert sorted(p.name for p in paths.product.iterdir()) == ["rev.py"]


# --- approval ---------------------------------------------------------------------------------


def test_a_held_out_file_edited_after_approval_stops_the_run_before_anything_is_spent(paths):
    write_held_out(paths, HP)
    s = sheet()
    with LedgerWriter(paths.ledger) as ledger:
        data = {
            "hashes": content_hashes(s, paths.checks),
            "held_out_hashes": held_out.hashes(paths.held_out),
        }
        ledger.append(
            Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
    (paths.held_out / "test_h01.py").write_text(
        "from rev import reverse\n\ndef test_x():\n    pass\n"
    )
    worker = Script(step(GOOD, "done"))
    with pytest.raises(NotApprovedError):
        run(paths, worker, approve=False)
    assert worker.specs == [] and events_of(paths, EventType.SLICE_START) == []


class Tamper:
    """Wraps a worker; after its first slice runs `edit()`."""

    def __init__(self, worker, edit):
        self.worker, self.edit = worker, edit

    def __call__(self, spec, workspace, log_path, *, env):
        result = self.worker(spec, workspace, log_path, env=env)
        if len(self.worker.specs) == 1:
            self.edit()
        return result


@pytest.mark.parametrize("how", ["edit", "delete", "add"])
def test_a_held_out_file_changed_mid_run_stops_it_like_an_edited_visible_check(paths, how):
    write_held_out(paths, HP)
    files = {"edit": lambda: (paths.held_out / "test_h01.py").write_text(HP + "\n"),
             "delete": lambda: (paths.held_out / "test_h01.py").unlink(),
             "add": lambda: (paths.held_out / "test_h09.py").write_text(HP)}  # fmt: skip
    worker = Script(step(HALF, cost=30_000), step(GOOD, "done"))
    report, _ = run(paths, Tamper(worker, files[how]))
    assert report.stopped == (
        "stopped: the term sheet or a check changed after the investor approved it"
    )
    assert len(worker.specs) == 1 and held_results(paths) == []
    assert total(read_events(paths.ledger)).cost_micros == 30_000
    assert (report.held_out_passed, report.held_out_total) == (0, 1) and not report.all_passed


def test_a_held_out_file_changed_during_the_products_own_gate_is_never_graded(paths):
    def gate_then_tamper(workspace, checks_dir, checks):
        results = run_gate(workspace, checks_dir, checks)
        if workspace == paths.product and checks_dir == paths.checks:
            (paths.held_out / "test_h01.py").write_text("def test_x():\n    assert True\n")
        return results

    report, _ = run(paths, Script(step(GOOD, "done")), codes=(HP,), gate=gate_then_tamper)
    assert held_results(paths) == []
    assert (report.passed, report.held_out_passed, report.held_out_total) == (2, 0, 1)
    assert not report.all_passed


def test_an_approved_but_unreadable_manifest_is_refused_before_anything_is_spent(paths):
    write_held_out(paths, HP)
    (paths.held_out / "manifest.json").write_text("{")
    worker = Script(step(GOOD, "done"))
    with pytest.raises(NotApprovedError, match="held-out checks cannot be read"):
        run(paths, worker)
    assert worker.specs == []


# --- per-worker decisions never see them ------------------------------------------------------


def result(check, status, **extra):
    data = {"check": check, "status": status, "detail": "", "scope": "held_out"} | extra
    return Event(run="r1", round=1, actor="gate", event=EventType.CHECK_RESULT, data=data)


def test_run_state_and_slice_history_ignore_held_out_results_even_ones_shaped_like_a_workers():
    base = worker_events()
    noise = [
        result("c01", "passed"),
        result("c02", "passed", worker="w1", slice=1),  # shaped like a worker's own result
        result("h01", "passed", worker="w1", slice=1, task="t1"),
    ]
    assert run_state(base + noise, ["t1"]) == run_state(base, ["t1"])
    assert slice_history(base + noise) == slice_history(base)
    assert slice_history(base + noise)["w1"][0].passing == frozenset()


def worker_events():
    def event(kind, actor, **data):
        return Event(run="r1", round=1, actor=actor, event=kind, data=data)

    return [
        event(EventType.HIRED, "boss", worker="w1", task="t1", model="haiku"),
        event(EventType.SLICE_START, "worker:w1", slice=1, task="t1", cap_micros=1, session="s"),
        event(
            EventType.SLICE_END,
            "worker:w1",
            slice=1,
            task="t1",
            outcome="completed",
            status={"status": "continuing"},
            session_total_micros=1,
        ),  # fmt: skip
        event(
            EventType.CHECK_RESULT,
            "gate",
            check="c01",
            task="t1",
            status="failed",
            detail="",
            worker="w1",
            slice=1,
        ),  # fmt: skip
    ]


# --- configuration ----------------------------------------------------------------------------


def test_held_out_round_trips_through_the_recorded_configuration(paths):
    config = FirmConfig(held_out=3, model="haiku")
    assert config_data(config)["held_out"] == 3
    assert config_from_data(config_data(config)) == config
    run(paths, Script(step(GOOD, "done")), config=config, codes=(HP,))
    [started] = events_of(paths, EventType.STARTED)
    assert started.data["config"]["held_out"] == 3
    # a resume uses the configuration the run started with
    report, _ = run(paths, Script(), config=STARTED)
    assert report.held_out_total == 1


def test_a_configuration_recorded_before_held_out_existed_loads_with_it_off():
    data = config_data(FirmConfig())
    del data["held_out"]
    assert config_from_data(data).held_out == 0


@pytest.mark.parametrize("bad", [-1, 9, True, 2.0, "3", None])
def test_held_out_must_be_a_whole_number_from_zero_to_eight(bad):
    with pytest.raises(ValueError, match="held_out must be a whole number from 0 to 8"):
        FirmConfig(held_out=bad)
    with pytest.raises(ValueError, match="held_out must be"):
        config_from_data(config_data(FirmConfig()) | {"held_out": bad})


@pytest.mark.parametrize("ok", [0, 1, 8])
def test_zero_to_eight_are_accepted(ok):
    assert FirmConfig(held_out=ok).held_out == ok


# --- the examiner in a whole run ----------------------------------------------------------------

RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.02,
    "modelUsage": {"m": {"inputTokens": 100, "outputTokens": 50, "cacheReadInputTokens": 7}},
}
FAKE = f"""#!{sys.executable}
import os, sys
if os.environ.get("FAKE_FAIL"):
    sys.exit(1)
print({BOSS_INIT_LINE!r})
print(os.environ["FAKE_OUTPUT"])
"""
EXAMINED = {
    "checks": [
        {"id": "h01", "source": HS, "code": HP},
        {"id": "h02", "source": "Reverse a string", "code": HF},
    ]
}


@pytest.fixture
def examiner_env(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE)
    cli.chmod(0o755)

    def make(output, fail=False):
        text = json.dumps(RESULT | {"structured_output": output})
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_OUTPUT": text}
        return env | ({"FAKE_FAIL": "1"} if fail else {}), str(cli)

    return make


def whole_run(paths, examiner_env, output, *, fail=False, budget=500_000):
    """The boss has drafted: the examiner is called, the investor reviews, then the firm runs."""
    s = dataclasses.replace(sheet(), idea=IDEA)
    s = dataclasses.replace(
        s, budget_micros=budget, rounds=(dataclasses.replace(s.rounds[0], budget_micros=budget),)
    )
    env, cli = examiner_env(output, fail)
    worker = Script(step(GOOD, "done"))
    config = FirmConfig(held_out=2, slice_micros=500_000)
    with LedgerWriter(paths.ledger) as ledger:
        said = []
        run_examiner(
            s, paths, ledger, "r1", n=2, env=env, model="haiku", executable=cli, say=said.append
        )
        approved = review_term_sheet(
            s, paths.checks, paths.root, ledger, "r1", ask=lambda _: "a", say=said.append,
            held_out_dir=paths.held_out,
        )  # fmt: skip
        assert approved is not None
        report = run_firm(
            approved, paths, ledger, "r1", env=ENV, config=config,
            ask=lambda _: "n", say=said.append, slice_runner=worker, sleep=lambda _: None,
        )  # fmt: skip
    return report, said, worker


def test_examiner_review_approval_and_grading_in_one_run(paths, examiner_env):
    report, said, _ = whole_run(paths, examiner_env, EXAMINED)
    assert (report.held_out_passed, report.held_out_total) == (1, 2)
    assert any("The examiner wrote 2 held-out checks" in line for line in said)
    assert any("HELD-OUT CHECKS" in line for line in said)  # shown with the term sheet
    [call] = events_of(paths, EventType.ROLE_CALL)
    assert call.actor == "role:examiner" and call.data["kept"] == 2
    [approval] = events_of(paths, EventType.APPROVED)
    assert set(approval.data["held_out_hashes"]) == {"manifest.json", "test_h01.py", "test_h02.py"}
    shown = render_report(build_report(read_events(paths.ledger)))
    assert "Held-out checks: 1 of 2 passed on the product; the workers never saw them." in shown
    assert "  h02  failed" in shown and "role:examiner" in shown


def test_the_examiners_spend_is_booked_and_shrinks_the_first_slices_cap(paths, examiner_env):
    _, _, worker = whole_run(paths, examiner_env, EXAMINED, budget=300_000)
    [call] = events_of(paths, EventType.ROLE_CALL)
    assert (call.cost_micros, call.round) == (20_000, 1)
    # 300,000 - the examiner's 20,000 - one reserve of 100,000: what a slice may be capped at
    assert worker.specs[0].cap_micros == 180_000
    events = read_events(paths.ledger)
    assert total(events).cost_micros == 20_000 + 10_000  # the call and the one scripted slice


def test_an_examiner_that_fails_is_recorded_and_the_run_goes_on_without_held_out_checks(
    paths, examiner_env
):
    report, said, worker = whole_run(paths, examiner_env, EXAMINED, fail=True)
    assert any(line.startswith("No held-out checks:") for line in said)
    [call] = events_of(paths, EventType.ROLE_CALL)
    assert (
        call.data["kept"] == 0
        and call.data["requested"] == 2
        and call.data["outcome"] != "completed"
    )
    assert not paths.held_out.exists()
    assert len(worker.specs) == 1
    assert (report.held_out_passed, report.held_out_total) == (0, 0) and report.all_passed
    shown = render_report(build_report(read_events(paths.ledger)))
    assert "Held-out checks: none. The examiner's call ended" in shown
    assert "the run went on without them." in shown


def test_an_examiner_output_the_gate_refuses_is_recorded_and_the_run_goes_on(paths, examiner_env):
    bad = {"checks": [dict(c, source="not in the idea at all") for c in EXAMINED["checks"]]}
    report, said, _ = whole_run(paths, examiner_env, bad)
    [call] = events_of(paths, EventType.ROLE_CALL)
    assert call.data["kept"] == 0 and "fragment of the idea" in call.data["problems"][0]
    assert call.cost_micros == 20_000  # the refused output was paid for
    assert report.all_passed and not paths.held_out.exists()
    shown = render_report(build_report(read_events(paths.ledger)))
    assert "Held-out checks: none. The examiner's output was not kept: " in shown
    assert json.loads(paths.examiner_refused.read_text()) == bad
