"""The investor key and the signature on approvals (docs/THREAT_MODEL.md, T46).

The claim under test: a worker that can edit the ledger, and recompute its hash chain, still
cannot produce an approval `require_approval` accepts, because it cannot read
`<project>/.boss/investor.key`. The tests cover the key file, the signature, every forgery the
chain alone would allow, the paths that keep the key away from a worker and from the gate, and
the limits that remain (`test_accepted_risk_*`).
"""

import dataclasses
import json
import os
import re
import stat
import subprocess
import threading
import uuid
from pathlib import Path

import pytest
from docs_support import run_cli
from test_gate_sandbox import ON, attempt, denied, requires_sandbox

from boss.approval import NotApprovedError, content_hashes, require_approval, review_term_sheet
from boss.firm import run_firm
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.rundir import RunPaths
from boss.sandbox import SandboxMode
from boss.signing import SigningError, key_path, load_key, load_or_create_key, signed, verify
from boss.termsheet import CheckSpec, Round, Task, TermSheet
from boss.worker import SliceSpec, build_command, worker_env

ROOT = Path(__file__).resolve().parent.parent
C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
C02 = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
SHEET = TermSheet(
    idea="Reverse a string.",
    budget_micros=500_000,
    rounds=(Round(1, 500_000, 2),),
    checks=(
        CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
        CheckSpec("c02", "empty string", "test_c02.py", "t1"),
    ),
    tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
)
HEX = re.compile(r"[0-9a-f]{64}")


@pytest.fixture
def project(tmp_path):
    """A project folder laid out as `boss fund` makes one, with the checks written and a run
    folder whose investor key therefore resolves."""
    run = RunPaths(tmp_path / "project" / ".boss" / "runs" / "r1")
    run.checks.mkdir(parents=True)
    (run.checks / "test_c01.py").write_text(C01)
    (run.checks / "test_c02.py").write_text(C02)
    return run


def approve(run: RunPaths) -> list[Event]:
    """The investor approves through the real review function; returns the ledger."""
    with LedgerWriter(run.ledger) as ledger:
        result = review_term_sheet(
            SHEET, run.checks, run.root, ledger, "r1",
            ask=lambda _: "a", say=lambda _: None, key_path=run.investor_key,
        )  # fmt: skip
        assert result is not None
    return read_events(run.ledger)


def check(run: RunPaths, events=None) -> None:
    require_approval(
        events if events is not None else read_events(run.ledger),
        SHEET, run.checks, key_path=run.investor_key,
    )  # fmt: skip


def rewrite(run: RunPaths, events: list[Event]) -> list[Event]:
    """What a worker with write access to the ledger can do: write any events it likes through
    the real writer, so the chain is recomputed and valid from the first line."""
    run.ledger.unlink()
    with LedgerWriter(run.ledger) as ledger:
        for event in events:
            ledger.append(event)
    return read_events(run.ledger)


def forged(run: RunPaths, **data) -> Event:
    hashes = {"hashes": content_hashes(SHEET, run.checks)}
    return Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=hashes | data)


# --- the key file ----------------------------------------------------------------------------


def test_the_key_is_created_once_with_mode_0600_and_is_not_regenerated(tmp_path):
    path = key_path(tmp_path)
    assert load_key(path) is None
    key = load_or_create_key(path)
    assert len(key) == 32 and HEX.fullmatch(path.read_text().strip())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_or_create_key(path) == key == load_key(path)
    assert [p.name for p in path.parent.iterdir()] == ["investor.key"]  # no temporary left over


def test_the_key_is_created_0600_whatever_the_umask(tmp_path):
    old = os.umask(0)
    try:
        path = key_path(tmp_path)
        load_or_create_key(path)
    finally:
        os.umask(old)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_two_threads_asking_at_once_end_up_with_one_key(tmp_path):
    path, found = key_path(tmp_path), []
    threads = [
        threading.Thread(target=lambda: found.append(load_or_create_key(path))) for _ in "abcd"
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(found) == 4 and len(set(found)) == 1 and found[0] == load_key(path)
    assert [p.name for p in path.parent.iterdir()] == ["investor.key"]


def test_a_key_readable_by_others_is_refused_and_not_widened(tmp_path):
    path = key_path(tmp_path)
    load_or_create_key(path)
    path.chmod(0o644)
    with pytest.raises(SigningError, match="chmod 600"):
        load_key(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644  # told, not silently changed


@pytest.mark.parametrize(
    "content", ["", "zz" * 32, "ab" * 31, "ab" * 33, "é" * 64, "not a key at all"]
)
def test_a_file_that_is_not_a_key_is_refused_without_quoting_it(tmp_path, content):
    path = key_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(content.encode())
    path.chmod(0o600)
    with pytest.raises(SigningError) as raised:
        load_key(path)
    assert content not in str(raised.value) or content == ""
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None or raised.value.__suppress_context__


def test_a_symlinked_or_non_regular_key_is_refused(tmp_path):
    real = tmp_path / "elsewhere.key"
    real.write_text("ab" * 32)
    real.chmod(0o600)
    path = key_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.symlink_to(real)
    with pytest.raises(SigningError):
        load_key(path)
    path.unlink()
    path.mkdir()
    with pytest.raises(SigningError):
        load_key(path)


def test_keys_differ_between_projects(tmp_path):
    a, b = (load_or_create_key(key_path(tmp_path / n)) for n in "ab")
    assert a != b


def test_the_key_stays_out_of_git(tmp_path):
    """`.boss/` and `*.key` are in .gitignore; this pins it so a key is never one `git add` away."""
    done = subprocess.run(
        ["git", "check-ignore", "-q", ".boss/investor.key"], cwd=ROOT, capture_output=True
    )
    if done.returncode == 128:
        pytest.skip("not a git checkout")
    assert done.returncode == 0


# --- signing ---------------------------------------------------------------------------------


def event_of(key, run="r1", round=0, **data):
    return Event(
        run=run, round=round, actor="investor", event=EventType.APPROVED,
        data=signed(key, run, round, data),
    )  # fmt: skip


def test_a_signature_verifies_and_changes_with_the_key():
    key, other = b"\x01" * 32, b"\x02" * 32
    event = event_of(key, hashes={"term_sheet": "ab"})
    assert verify(key, event) and not verify(other, event)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: dataclasses.replace(e, run="r2"),
        lambda e: dataclasses.replace(e, round=1),
        lambda e: dataclasses.replace(e, data={**e.data, "hashes": {"term_sheet": "ac"}}),
        lambda e: dataclasses.replace(e, data={**e.data, "added_checks": ["c03"]}),
        lambda e: dataclasses.replace(e, data={k: v for k, v in e.data.items() if k != "hashes"}),
    ],
)
def test_the_signature_covers_the_run_the_round_and_every_data_key(mutate):
    key = b"\x01" * 32
    event = event_of(key, hashes={"term_sheet": "ab"})
    assert verify(key, event) and not verify(key, mutate(event))


@pytest.mark.parametrize("sig", [None, "", 5, ["x"], "é" * 64, "A" * 64])
def test_a_malformed_signature_is_false_not_an_exception(sig):
    key = b"\x01" * 32
    event = event_of(key, hashes={})
    bad = dataclasses.replace(event, data={**event.data, "sig": sig})
    assert verify(key, bad) is False


def test_signing_does_not_change_the_data_it_was_given():
    data = {"hashes": {"a": "b"}}
    out = signed(b"\x01" * 32, "r", 0, data)
    assert data == {"hashes": {"a": "b"}} and set(out) == {"hashes", "sig"}
    assert signed(b"\x01" * 32, "r", 0, out) == out  # signing again ignores the old signature


# --- the real flow ---------------------------------------------------------------------------


def test_the_investors_approval_is_signed_and_verified_and_the_key_is_created_for_it(project):
    assert project.investor_key is not None and not project.investor_key.exists()
    events = approve(project)
    [approval] = [e for e in events if e.event is EventType.APPROVED]
    assert HEX.fullmatch(approval.data["sig"]) and approval.prev is not None
    check(project, events)
    assert stat.S_IMODE(project.investor_key.stat().st_mode) == 0o600


def test_the_key_never_reaches_the_ledger_the_screen_or_an_error(project):
    said = []
    with LedgerWriter(project.ledger) as ledger:
        review_term_sheet(
            SHEET, project.checks, project.root, ledger, "r1",
            ask=lambda _: "a", say=said.append, key_path=project.investor_key,
        )  # fmt: skip
    secret = project.investor_key.read_text().strip()
    assert secret not in project.ledger.read_text()
    assert secret not in "\n".join(said)
    assert secret not in (project.root / "term_sheet.json").read_text()
    project.investor_key.write_text(secret[:-2])  # now damaged: the error must not quote it
    with pytest.raises(NotApprovedError) as raised:
        check(project)
    assert secret[:-2] not in str(raised.value) and secret not in repr(raised.value)


def test_an_edit_to_the_signed_approval_is_refused_even_with_the_chain_recomputed(project):
    events = approve(project)
    edited = [
        dataclasses.replace(e, round=1) if e.event is EventType.APPROVED else e for e in events
    ]
    with pytest.raises(NotApprovedError, match="signature does not verify"):
        check(project, rewrite(project, edited))


def test_an_approval_forged_after_a_check_was_edited_is_refused(project):
    """The attack: change a check, then write an approval for the new content with a valid chain."""
    approve(project)
    (project.checks / "test_c01.py").write_text(C01.replace("'ba'", "'ab'"))
    with pytest.raises(NotApprovedError):  # the old approval no longer matches
        check(project)
    old = read_events(project.ledger)
    for forgery in (
        forged(project),  # no signature at all
        forged(project, sig="0" * 64),  # a made-up one
        forged(project, sig=signed(b"\x07" * 32, "r1", 0, {"hashes": {}})),  # the wrong key
    ):
        events = rewrite(project, [*old, forgery])
        assert events[-1].prev is not None
        with pytest.raises(NotApprovedError):
            check(project, events)


def test_the_firm_spends_nothing_on_a_forged_approval(project):
    approve(project)
    (project.checks / "test_c01.py").write_text(C01 + "\n# edited\n")
    rewrite(project, [*read_events(project.ledger), forged(project)])
    spent = []
    with LedgerWriter(project.ledger) as ledger, pytest.raises(NotApprovedError):
        run_firm(
            SHEET, project, ledger, "r1", env={}, say=lambda _: None,
            slice_runner=lambda *a, **k: spent.append(1),
        )  # fmt: skip
    assert spent == []


def test_a_whole_ledger_rewritten_from_the_first_line_with_a_forged_approval_is_refused(project):
    approve(project)
    (project.checks / "test_c02.py").write_text(C02.replace("''", "'x'"))
    only_the_forgery = rewrite(project, [forged(project)])
    assert only_the_forgery[0].prev is not None
    with pytest.raises(NotApprovedError, match="no matching|signature"):
        check(project, only_the_forgery)


def test_a_signature_copied_onto_other_content_is_refused(project):
    [approval] = [e for e in approve(project) if e.event is EventType.APPROVED]
    (project.checks / "test_c01.py").write_text(C01 + "\n# edited\n")
    changed = forged(project, sig=approval.data["sig"])
    with pytest.raises(NotApprovedError, match="signature does not verify"):
        check(project, rewrite(project, [changed]))


def test_an_approval_moved_to_another_run_is_refused(project):
    [approval] = [e for e in approve(project) if e.event is EventType.APPROVED]
    moved = dataclasses.replace(approval, run="r2")
    with pytest.raises(NotApprovedError, match="signature does not verify"):
        check(project, rewrite(project, [moved]))


def test_a_signed_approval_whose_key_was_deleted_or_replaced_is_refused(project):
    events = approve(project)
    project.investor_key.unlink()
    with pytest.raises(NotApprovedError, match="signature does not verify"):
        check(project, events)
    load_or_create_key(project.investor_key)  # a fresh key: the old signature cannot verify
    with pytest.raises(NotApprovedError, match="signature does not verify"):
        check(project, events)


def test_a_damaged_key_stops_the_check_instead_of_skipping_it(project):
    events = approve(project)
    project.investor_key.chmod(0o644)
    with pytest.raises(NotApprovedError, match="chmod 600"):
        check(project, events)


# --- older ledgers and runs without a key ----------------------------------------------------


def test_an_unsigned_approval_older_than_the_chain_still_loads_even_when_a_key_exists(project):
    load_or_create_key(project.investor_key)  # the project got a key later, from another run
    old = project.ledger
    line = forged(project).to_json()  # no `prev`: written before the chain existed
    old.write_text(line + "\n")
    events = read_events(old)
    assert events[0].prev is None
    check(project, events)


def test_a_run_folder_that_is_not_in_a_project_has_no_key_and_needs_no_signature(tmp_path):
    run = RunPaths(tmp_path / "run")
    assert run.investor_key is None
    run.checks.mkdir(parents=True)
    (run.checks / "test_c01.py").write_text(C01)
    (run.checks / "test_c02.py").write_text(C02)
    with LedgerWriter(run.ledger) as ledger:
        ledger.append(forged(run))
    require_approval(read_events(run.ledger), SHEET, run.checks, key_path=run.investor_key)


def test_no_key_file_means_an_unsigned_approval_is_accepted(project):
    with LedgerWriter(project.ledger) as ledger:
        ledger.append(forged(project))
    assert not project.investor_key.exists()
    check(project)


def test_accepted_risk_a_ledger_rewritten_without_the_chain_and_signatures_loads_as_an_old_one(
    project,
):
    # Whoever can rewrite the whole file and the key can do anything (T29): this pins the limit of
    # "older ledgers still load". A worker cannot reach the key (below), so for it the downgrade
    # needs the key file to be gone as well; with a key present the unchained line is accepted.
    approve(project)
    (project.checks / "test_c01.py").write_text(C01 + "\n# edited\n")
    project.ledger.write_text(forged(project).to_json() + "\n")
    events = read_events(project.ledger)
    assert events[0].prev is None and project.investor_key.exists()
    check(project, events)


# --- what keeps the key away from a worker and from the gate ---------------------------------


def test_the_key_is_not_in_the_run_folder_or_any_workspace_the_gate_or_the_handoff_copies(project):
    key = project.investor_key
    assert key is not None
    for inside in (project.root, project.checks, project.held_out, project.product,
                   project.workspace("w1"), project.root / "logs"):  # fmt: skip
        assert not key.is_relative_to(inside), inside
    assert key.parent == project.root.parent.parent  # `<project>/.boss`, beside `runs/`


def test_a_workers_tool_rules_reach_only_its_own_folder_and_it_is_given_no_other_folder():
    spec = SliceSpec(
        session_id=uuid.uuid4(), resume=False, prompt="Build it.", model="haiku", cap_micros=300_000
    )
    argv = build_command(spec, api_key=False)
    rules = argv[argv.index("--allowedTools") + 1].split()
    assert rules and all(re.fullmatch(r"(Read|Write|Edit)\(\./\*\*\)", r) for r in rules), rules
    assert argv[argv.index("--tools") + 1] == "Read,Write,Edit"  # no shell to `cat` it with
    assert "--add-dir" not in argv and "--dangerously-skip-permissions" not in argv


def test_the_worker_environment_carries_no_path_to_the_key_and_no_key():
    environ = {"PATH": "/usr/bin", "HOME": "/h", "BOSS_INVESTOR_KEY": "x", "OTHER": "y"}
    assert worker_env(environ).keys() <= {"HOME", "PATH", "USER", "LANG", "TMPDIR",
                                          "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY"}  # fmt: skip


@requires_sandbox
def test_a_check_run_by_the_gate_cannot_read_the_key(tmp_path):
    path = key_path(tmp_path / "project")
    load_or_create_key(path)
    body = f"open({str(path)!r}).read()"
    assert attempt(tmp_path, body, SandboxMode.OFF) == "allowed"  # the probe is not vacuous
    assert denied(attempt(tmp_path, body, ON))


@requires_sandbox
def test_a_check_run_by_the_gate_cannot_replace_the_key_either(tmp_path):
    path = key_path(tmp_path / "project")
    load_or_create_key(path)
    before = path.read_bytes()
    body = f"open({str(path)!r}, 'w').write('x')"
    assert denied(attempt(tmp_path, body, ON))
    assert path.read_bytes() == before


def test_accepted_risk_without_a_sandbox_the_gate_runs_code_that_can_read_the_key(tmp_path):
    path = key_path(tmp_path / "project")
    key = load_or_create_key(path)
    body = f"open({str(path)!r}).read()"
    assert attempt(tmp_path, body, SandboxMode.OFF) == "allowed"
    assert key  # which is why the claim is "a confined worker", and T39 says what confines it


# --- the whole thing through the real CLI ----------------------------------------------------


def test_fund_signs_its_approval_and_the_run_it_builds_verifies_it(tmp_path):
    code, run_dir, said = run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"])
    assert code == 0, said
    run = RunPaths(run_dir)
    events = read_events(run.ledger)
    approvals = [e for e in events if e.event is EventType.APPROVED and "hashes" in e.data]
    assert approvals and all(e.data["sig"] and e.prev for e in approvals)
    secret = run.investor_key.read_text().strip()
    assert secret not in run.ledger.read_text() and secret not in "\n".join(said)
    assert stat.S_IMODE(run.investor_key.stat().st_mode) == 0o600
    assert not any(
        json.loads(line).get("prev") is None for line in run.ledger.read_text().split("\n") if line
    )


def test_the_full_chain_of_a_real_run_reads_back_clean_and_in_order(tmp_path):
    _, run_dir, _ = run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"])
    events = read_events(run_dir / "ledger.jsonl")
    assert len(events) >= 5 and events[0].prev == "0" * 64
