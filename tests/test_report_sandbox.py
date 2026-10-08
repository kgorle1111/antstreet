"""Whether the checks ran sandboxed (T39): the firm records the gate's flag on every check result,
and the report says it, warns on an unconfined run, and still renders a ledger without the key."""

import dataclasses

import pytest
from test_firm import C01, C02, C03, GOOD, Script, step
from test_firm_held_out import HP, run

from antstreet.gate import run_gate
from antstreet.ledger import Event, EventType, read_events
from antstreet.report import build_report, render_report
from antstreet.rundir import RunPaths

NOT_RECORDED = "Checks ran sandboxed: not recorded (a ledger from before the flag existed)."


def result(check, sandboxed="absent", **extra) -> Event:
    data = {"check": check, "status": "passed", "detail": "1 passed"} | extra
    if sandboxed != "absent":
        data["sandboxed"] = sandboxed
    return Event(run="r1", round=1, actor="gate", event=EventType.CHECK_RESULT, data=data)


def line(events) -> str | None:
    out = render_report(build_report(events))
    found = [x for x in out.splitlines() if "sandboxed:" in x]
    assert len(found) <= 1
    return found[0] if found else None


def test_all_sandboxed_is_one_plain_line():
    assert line([result("c01", True), result("c02", True)]) == "Checks ran sandboxed: 2 of 2."


def test_an_unconfined_run_is_a_warning_naming_the_count():
    got = line([result("c01", True), result("c02", False), result("c03", False)])
    assert got == (
        "WARNING: Checks ran sandboxed: 1 of 3 (2 UNCONFINED); see T39 in the threat model."
    )


def test_an_unconfined_run_a_later_run_superseded_still_warns():
    got = line([result("c01", False), result("c01", True)])
    assert got is not None and got.startswith("WARNING:") and "1 of 2" in got


def test_a_ledger_without_the_key_says_not_recorded_and_does_not_fail():
    assert line([result("c01"), result("c02")]) == NOT_RECORDED


def test_a_mixed_ledger_counts_the_old_events_as_not_recorded():
    assert line([result("c01", True), result("c02")]) == (
        "Checks ran sandboxed: 1 of 2 (1 not recorded)."
    )


@pytest.mark.parametrize("junk", ["yes", 1, None, "false"])
def test_a_flag_that_is_not_a_bool_is_not_recorded_never_a_pass(junk):
    assert line([result("c01", junk)]) == NOT_RECORDED


def test_held_out_results_count_too():
    got = line([result("c01", True), result("h01", False, scope="held_out")])
    assert got is not None and "UNCONFINED" in got


def test_an_incomplete_check_result_is_not_counted():
    broken = Event(
        run="r1", round=1, actor="gate", event=EventType.CHECK_RESULT, data={"sandboxed": False}
    )
    assert line([result("c01", True), broken]) == "Checks ran sandboxed: 1 of 1."


def test_a_run_with_no_check_results_prints_no_line():
    assert line([Event(run="r1", round=0, actor="boss", event=EventType.STARTED)]) is None


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


@pytest.mark.parametrize("flag", [True, False])
def test_the_firm_records_the_gates_flag_on_slice_product_and_held_out_results(paths, flag):
    def gate(*args, **kwargs):
        return [dataclasses.replace(r, sandboxed=flag) for r in run_gate(*args, **kwargs)]

    run(paths, Script(step(GOOD, "done")), codes=(HP,), gate=gate)
    results = [e for e in read_events(paths.ledger) if e.event is EventType.CHECK_RESULT]
    scopes = {e.data.get("scope", "slice") for e in results}
    assert scopes == {"slice", "product", "held_out"}
    assert [e.data["sandboxed"] for e in results] == [flag] * len(results)
