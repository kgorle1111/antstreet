"""Where `--spec` and `boss audit` meet: one ledger holds a signed approval carrying the coverage
summary (`data.spec`) and a signed `audited` verdict. Editing either, or adding a verdict without
the key, is refused whichever comes first (docs/THREAT_MODEL.md, T54 and T57)."""

import hashlib
import json

import pytest
from test_approval_spec import EMPTY, IDEA, TYPE_OK, approve

from antstreet import spec
from antstreet.ledger import (
    GENESIS,
    Event,
    EventType,
    LedgerUnverifiedError,
    LedgerWriter,
    audited,
    read_events,
)
from antstreet.rundir import RunPaths

VERDICT = {"base": "a" * 40, "head": "b" * 40, "verdict": "unrefuted", "claim": "done"}


@pytest.fixture
def run(tmp_path):
    run = RunPaths(tmp_path / "project" / ".boss" / "runs" / "r1")
    run.checks.mkdir(parents=True)
    (run.checks / "test_c01.py").write_text(EMPTY)
    (run.checks / "test_c02.py").write_text(TYPE_OK)
    run.rules.write_text(spec.dumps(spec.split(IDEA)), encoding="utf-8")
    approve(run)  # a signed `approved` event with the coverage summary
    with run.writer() as ledger:
        ledger.append(Event(run="r1", round=0, actor="gate", event=EventType.AUDITED, data=VERDICT))
    return run


def rewrite(run, index, edit):
    """Edit line `index` of the ledger and relink every `prev`, as someone without the key could."""
    lines = [json.loads(x) for x in run.ledger.read_text().splitlines()]
    edit(lines[index])
    prev, out = GENESIS, []
    for line in lines:
        line.pop("mac", None)  # a line signature cannot be remade without the key
        line["prev"] = prev
        raw = json.dumps(line, sort_keys=True)
        prev = hashlib.sha256(raw.encode()).hexdigest()
        out.append(raw + "\n")
    run.ledger.write_text("".join(out))


def test_both_kinds_of_signed_line_verify_together(run):
    approved, verdict = run.events()
    assert approved.data["spec"]["uncovered"] == ["R04"] and verdict.data["sig"].startswith("v2:")
    assert audited([approved, verdict]) == [verdict]


def test_a_forged_coverage_summary_is_refused_beside_a_valid_verdict(run):
    rewrite(run, 0, lambda line: line["data"]["spec"].update(uncovered=[]))
    with pytest.raises(LedgerUnverifiedError, match="investor `approved` event"):
        run.events()


def test_an_edited_verdict_is_refused_beside_a_valid_spec_approval(run):
    rewrite(run, 1, lambda line: line["data"].update(verdict="refuted"))
    with pytest.raises(LedgerUnverifiedError, match="`audited` event by gate"):
        run.events()


def test_a_keyless_verdict_appended_after_a_spec_approval_is_refused(run):
    with LedgerWriter(run.ledger) as keyless:
        keyless.append(
            Event(run="r1", round=0, actor="gate", event=EventType.AUDITED, data=VERDICT)
        )
    assert len(read_events(run.ledger)) == 3
    with pytest.raises(LedgerUnverifiedError, match="`audited` event by gate"):
        run.events()
