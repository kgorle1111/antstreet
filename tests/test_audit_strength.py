"""Check strength in `boss audit check`: the counted checks against mutants of the change.

The sealed checks here are two strong ones and a weak one that only calls the new function and
asserts nothing about what it gives back. The head is right, so the verdict is unrefuted; strength
must then tell the two kinds of check apart, and must never change the verdict.
"""

import shutil

import pytest
from audit_support import C01, C02, DRAFT, Audit, branch, later
from sandbox_support import working_sandbox

import antstreet.audit_check as audit_check
from antstreet.audit import CheckState, Observed
from antstreet.gate import GateError
from antstreet.ledger import EventType, audited
from antstreet.rundir import Recorder, RunPaths
from antstreet.sandbox import SandboxMode

TOOL = working_sandbox()
needs_sandbox = pytest.mark.skipif(TOOL is None, reason="no working OS sandbox on this machine")
WEAK = "from slug import collapse\n\n\ndef test_collapse_returns():\n    collapse('a b')\n"
STRENGTH_DRAFT = {
    "tasks": DRAFT["tasks"],
    "checks": [
        {"description": "runs of symbols become one hyphen", "task": "t1", "code": C01},
        {"description": "hyphens are trimmed at both ends", "task": "t1", "code": C02},
        {"description": "collapse can be called", "task": "t1", "code": WEAK},
    ],
}
# Right. Its changed lines give six mutants: the two `return`s to None, and on the length guard
# `>` to `>=`, 200 to 201, the condition negated and the `raise` dropped. A strong check kills the
# returns and the negation; the other three change nothing a short input shows (equivalent mutants
# for these checks). The weak check survives all six.
HEAD = (
    "import re\n\n\ndef collapse(text):\n    return re.sub(r'[^a-z0-9]+', '-', text)\n\n\n"
    "def slugify(text):\n    if len(text) > 200:\n        raise ValueError('too long')\n"
    "    return collapse(text.lower()).strip('-')\n\n\n"
    "def shout(text):\n    return text.upper()\n"
)


@pytest.fixture(scope="module")
def sealed(tmp_path_factory):
    audit = Audit(tmp_path_factory.mktemp("strength"))
    audit.set_draft(STRENGTH_DRAFT)
    code, said = audit.plan()
    assert code == 0, said
    assert "3 of 3 checks will be counted" in said  # the weak one fails on the base: no collapse
    audit.rid = audit.run_id()
    branch(audit.repo, "right", {"slug.py": HEAD}, later())
    return audit


@pytest.fixture
def store(sealed, tmp_path):
    copy = tmp_path / "store"
    shutil.copytree(sealed.store, copy)
    return copy


def check(sealed, store, *extra, **env):
    return sealed.check(sealed.rid, "right", "--claim", "done", *extra, BOSS_AUDIT_HOME=str(store),
                        **env)  # fmt: skip


def events(sealed, store):
    return audited(RunPaths(store / ".boss" / "runs" / sealed.rid).events())


@needs_sandbox
def test_a_strong_check_kills_mutants_and_a_weak_one_kills_none_and_is_flagged(sealed, store):
    code, said = check(sealed, store)
    assert code == 0 and "Verdict: UNREFUTED" in said, said
    assert "Check strength (advisory, never part of the verdict): 6 mutants" in said
    assert "  c01 kills 3/6\n" in said and "  c02 kills 3/6\n" in said
    assert "  c03 kills 0/6: WEAK, it would pass broken code" in said
    assert "not a catch rate" in said
    [event] = events(sealed, store)
    assert event.data["strength"] == {
        "mutants": 6, "found": 6, "killed": {"c01": 3, "c02": 3, "c03": 0}, "note": "",
    }  # fmt: skip


@needs_sandbox
def test_strength_never_changes_the_verdict(sealed, store):
    assert check(sealed, store)[0] == 0
    assert check(sealed, store, "--no-strength")[0] == 0
    measured, skipped = events(sealed, store)
    assert skipped.data["strength"] is None and measured.data["strength"]["mutants"] == 6

    def verdict(e):
        return {k: v for k, v in e.data.items() if k not in ("strength", "sig")}

    assert verdict(measured) == verdict(skipped)


@needs_sandbox
def test_the_report_shows_strength_and_flags_the_weak_check(sealed, store):
    check(sealed, store)
    code, said = sealed.run("report", BOSS_AUDIT_HOME=str(store))
    assert code == 0 and "check strength, kills of 6 mutants: c01 3, c02 3, c03 0 WEAK" in said


@needs_sandbox
def test_the_time_limit_stops_before_the_next_mutant_and_says_so(sealed, store):
    verdict = audit_check.check(
        sealed.rid, "right", repo=sealed.repo, store=store, claim="done", strength_timeout_s=0
    )
    assert verdict.verdict == "unrefuted" and verdict.strength is not None
    assert verdict.strength.mutants == 0 and "stopped at the 0s limit after 0 of 6" in (
        verdict.strength.note
    )


def test_without_a_sandbox_no_mutant_runs_and_the_verdict_still_stands(sealed, store, monkeypatch):
    monkeypatch.setattr(audit_check, "sandbox_available", lambda: False)
    code, said = check(sealed, store)
    assert code == 0 and "Verdict: UNREFUTED" in said
    assert "mutants run only inside an OS sandbox" in said and "kills" not in said
    [event] = events(sealed, store)
    assert event.data["strength"]["mutants"] == 0


def test_mutants_are_run_through_the_gate_with_the_sandbox_required(tmp_path, monkeypatch):
    base, head = tmp_path / "base", tmp_path / "head"
    base.mkdir()
    head.mkdir()
    (base / "m.py").write_text("def f(x):\n    return x\n")
    (head / "m.py").write_text("def f(x):\n    return x + 1\n")
    calls = []

    def gate(tree, paths, sheet, known, **kw):
        calls.append((kw["sandbox"], (tree / "m.py").read_text()))
        return {"c01": Observed(CheckState.FAILING, "")}

    monkeypatch.setattr(audit_check, "sandbox_available", lambda: True)
    monkeypatch.setattr(audit_check, "run_checks", gate)
    found = audit_check.measure_strength(base, head, None, None, frozenset(), ["c01"])
    assert (found.mutants, dict(found.killed)) == (3, {"c01": 3})
    assert {mode for mode, _ in calls} == {SandboxMode.REQUIRE}
    assert [text for _, text in calls] == [
        "def f(x):\n    return",  # a bare return: None
        "def f(x):\n    return x - 1",
        "def f(x):\n    return x + 2",
    ]
    assert (head / "m.py").read_text() == "def f(x):\n    return x + 1\n"  # put back

    monkeypatch.setattr(audit_check, "sandbox_available", lambda: False)
    calls.clear()
    refused = audit_check.measure_strength(base, head, None, None, frozenset(), ["c01"])
    assert calls == [] and refused.mutants == 0 and "OS sandbox" in refused.note


def test_a_ledger_written_before_strength_still_verifies_and_reports(sealed, store):
    paths = RunPaths(store / ".boss" / "runs" / sealed.rid)
    old = {
        "agent": None, "base": sealed.base, "blocked": [], "claim": "done",
        "claim_mode": "pre_registered", "claim_text_sha256": None, "counted": 3, "failed": [],
        "head": "a" * 40, "leaks": [], "regressions": [], "seal": "b" * 64, "tests_deleted": [],
        "verdict": "unrefuted",
    }  # fmt: skip
    with paths.writer() as ledger:
        Recorder(ledger, sealed.rid, 0)("gate", EventType.AUDITED, data=old)
    [event] = events(sealed, store)  # verified against the store's key
    assert "strength" not in event.data
    code, said = sealed.run("report", BOSS_AUDIT_HOME=str(store))
    assert code == 0 and "unrefuted, 3 counted" in said and "check strength" not in said


def test_a_crash_while_measuring_strength_never_costs_the_verdict(sealed, store, monkeypatch):
    def boom(*args, **kwargs):
        raise GateError("the gate fell over on a mutant")

    monkeypatch.setattr(audit_check, "measure_strength", boom)
    code, said = check(sealed, store)
    assert code == 0 and "Verdict: UNREFUTED" in said
    [event] = events(sealed, store)
    assert event.data["verdict"] == "unrefuted" and event.data["strength"]["mutants"] == 0
    assert event.data["strength"]["note"].startswith("not measured: GateError")
