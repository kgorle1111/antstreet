"""`boss audit report`: verdicts per run, the false-pass rate and interval, modes kept apart."""

from datetime import timedelta

import pytest
from audit_support import (
    HANGS_SLUG,
    LONG_AGO,
    NEEDS_LIB_SLUG,
    RIGHT_SLUG,
    WRONG_SLUG,
    Audit,
    branch,
    later,
    short_timeout_for_hangs,
)

from antstreet.audit_report import Observation, collect, render, wilson


@pytest.fixture(scope="module")
def audited(tmp_path_factory):
    audit = Audit(tmp_path_factory.mktemp("report"))
    assert audit.plan()[0] == 0
    rid = audit.run_id()
    branch(audit.repo, "good", {"slug.py": RIGHT_SLUG}, later())
    branch(audit.repo, "bad", {"slug.py": WRONG_SLUG}, later())
    branch(audit.repo, "needs_lib", {"slug.py": NEEDS_LIB_SLUG}, later())
    branch(audit.repo, "old_good", {"slug.py": RIGHT_SLUG}, LONG_AGO + timedelta(days=1))
    for head, agent, claim in [
        ("good", "agent-a", "done"),
        ("bad", "agent-a", "done"),
        ("needs_lib", "agent-a", "done"),  # inconclusive: left out of the rate
        ("bad", "agent-a", "none"),  # no claim: left out of the rate; a later verdict, same head
        ("old_good", "agent-a", "done"),  # post-hoc
        ("bad", "agent-b", "done"),
    ]:
        assert audit.check(rid, head, "--claim", claim, "--agent", agent)[0] in (0, 3)
    audit.rid = rid
    return audit


def test_each_verdict_is_listed_under_its_run_with_its_mode(audited):
    code, said = audited.run("report")
    assert code == 0 and f"Run {audited.rid}" in said
    assert "[agent-a] pre-registered: unrefuted, 2 counted" in said
    assert "[agent-b] pre-registered: refuted, failed c01, c02 of 2 counted" in said
    assert "[agent-a] pre-registered: inconclusive, 2 counted" in said
    assert "[agent-a] pre-registered: no_claim, failed c01, c02 of 2 counted" in said
    assert "[agent-a] post-hoc: unrefuted, 2 counted" in said


def test_a_later_verdict_on_the_same_head_and_agent_replaces_the_earlier_one(audited):
    code, said = audited.run("report", "--agent", "agent-a")
    assert code == 0
    # `bad` was audited by agent-a twice, as done and then with no claim: one verdict is shown
    assert said.count("[agent-a] pre-registered: refuted") == 0
    assert said.count("[agent-a] pre-registered: no_claim") == 1


def test_false_pass_rate_is_per_agent_and_mode_with_a_wilson_interval(audited):
    code, said = audited.run("report", "--all")
    assert code == 0
    rows = {line.split(" | ")[0] + " | " + line.split(" | ")[1]: line for line in said.splitlines()
            if line.startswith("agent-")}  # fmt: skip
    # agent-a, pre-registered: good unrefuted, needs_lib inconclusive, bad no_claim: 0 of 1 judged
    assert rows["agent-a | pre-registered"] == (
        "agent-a | pre-registered | 0 | 1 | 1 | 1 | 0% (0/1) | 0% to 79%"
    )
    assert rows["agent-a | post-hoc"] == "agent-a | post-hoc | 0 | 1 | 0 | 0 | 0% (0/1) | 0% to 79%"
    assert rows["agent-b | pre-registered"] == (
        "agent-b | pre-registered | 1 | 0 | 0 | 0 | 100% (1/1) | 21% to 100%"
    )
    assert "agent-b | post-hoc" not in rows  # a mode with no verdicts has no row


def test_pre_registered_and_post_hoc_are_never_pooled(audited):
    _, said = audited.run("report", "--all")
    assert "pre-registered and post-hoc rows are separate" in said
    assert "Post-hoc rows are not pre-registered" in said and "can be forged" in said
    assert "agent-a | all" not in said and "pooled" not in said.replace("never pooled", "")


def test_the_rate_is_presented_as_a_floor(audited):
    _, said = audited.run("report")
    assert "A floor" in said and "about 60%" in said and "at least what is shown" in said


def test_the_agent_filter_keeps_only_that_agents_verdicts(audited):
    _, said = audited.run("report", "--all", "--agent", "agent-b")
    assert "agent-b | pre-registered" in said and "agent-a" not in said


def test_a_store_with_no_runs_and_an_unknown_run_are_refused(tmp_path):
    audit = Audit(tmp_path)
    assert audit.run("report")[0] == 1
    code, said = audit.run("report", "--all")
    assert code == 0 and "No audit verdicts yet" in said
    assert audit.plan()[0] == 0
    code, said = audit.run("report", "nope")
    assert code == 1 and "No audit run 'nope'" in said
    code, said = audit.run("report")
    assert code == 0 and "No audit verdicts yet" in said  # a sealed run nobody has checked yet


def test_collect_reads_only_verified_gate_verdicts(audited):
    seen = collect(audited.store, [audited.rid])
    assert len(seen) == 5 and {o.agent for o in seen} == {"agent-a", "agent-b"}


@pytest.mark.parametrize(
    ("refuted", "n", "low", "high"),
    [(0, 1, 0.0, 0.7935), (1, 1, 0.2065, 1.0), (1, 2, 0.0945, 0.9055), (10, 20, 0.2993, 0.7007),
     (0, 10, 0.0, 0.2775), (3, 10, 0.1078, 0.6032)],
)  # fmt: skip
def test_wilson_matches_the_published_score_interval(refuted, n, low, high):
    got = wilson(refuted, n)
    assert got is not None
    assert got[0] == pytest.approx(low, abs=5e-4) and got[1] == pytest.approx(high, abs=5e-4)


@pytest.mark.parametrize(("refuted", "n"), [(0, 0), (1, 0), (-1, 3), (4, 3)])
def test_wilson_of_nothing_or_nonsense_is_none(refuted, n):
    assert wilson(refuted, n) is None


def test_the_same_counts_in_two_modes_stay_in_two_rows():
    def obs(mode, verdict):
        return Observation("r", "a", verdict[:1] + mode[:1], verdict, mode, 2, ())

    rows = [obs("pre_registered", "refuted"), obs("post_hoc", "unrefuted"),
            obs("post_hoc", "unrefuted")]  # fmt: skip
    text = render(rows)
    assert "a | pre-registered | 1 | 0 | 0 | 0 | 100% (1/1)" in text
    assert "a | post-hoc | 0 | 2 | 0 | 0 | 0% (0/2)" in text


def test_a_forged_audited_line_makes_the_report_refuse(audited, tmp_path):
    import shutil

    from antstreet.ledger import Event, EventType, LedgerWriter, read_events
    from antstreet.ledger import audited as gate_verdicts
    from antstreet.rundir import RunPaths

    copy = tmp_path / "store"
    shutil.copytree(audited.store, copy)
    paths = RunPaths(copy / ".boss" / "runs" / audited.rid)
    before = len(gate_verdicts(read_events(paths.ledger)))
    forged = Event(
        run=audited.rid, round=0, actor="gate", event=EventType.AUDITED,
        data={"verdict": "unrefuted", "claim": "done", "head": "c" * 40, "agent": "agent-a"},
    )  # fmt: skip
    with LedgerWriter(paths.ledger) as keyless:  # chains correctly; only the key can sign
        keyless.append(forged)
    assert len(gate_verdicts(read_events(paths.ledger))) == before + 1
    code, said = audited.run("report", "--all", BOSS_AUDIT_HOME=str(copy))
    assert code == 1 and "`audited` event by gate whose signature does not verify" in said


def test_a_head_timeout_is_listed_as_inconclusive_and_left_out_of_the_rate(tmp_path, monkeypatch):
    audit = Audit(tmp_path)
    assert audit.plan()[0] == 0
    branch(audit.repo, "hangs", {"slug.py": HANGS_SLUG}, later())
    short_timeout_for_hangs(monkeypatch)
    assert audit.check(audit.run_id(), "hangs", "--claim", "done", "--agent", "agent-a")[0] == 3
    code, said = audit.run("report")
    assert code == 0 and "[agent-a] pre-registered: inconclusive, 2 counted" in said
    assert "refuted" not in said.split("False-pass")[0].replace("false-pass", "")
