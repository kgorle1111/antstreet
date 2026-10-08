"""One real run against the actual CLI and model. Opt-in: costs a few cents.

BOSS_LIVE=1 uv run pytest tests/test_end_to_end.py -v
"""

import os

import pytest

from antstreet.cli import EXIT_INCOMPLETE, EXIT_OK, main
from antstreet.ledger import EventType, read_events, total
from antstreet.report import build_report, render_report

pytestmark = pytest.mark.skipif(
    os.environ.get("BOSS_LIVE") != "1", reason="live model call; set BOSS_LIVE=1 to run"
)

IDEA = (
    "A function count_vowels(text) that returns how many vowels (a, e, i, o, u, in either case) "
    "the text contains."
)
BUDGET = "0.40"
# The boss call is capped at $0.25 and the worker slice at 80% of the budget, each of which the
# CLI may overshoot by one response, so total spend must stay well under this.
SPEND_CEILING_MICROS = 900_000


def test_fund_builds_an_unseen_idea_and_the_report_matches_the_ledger(tmp_path):
    code = main(
        ["fund", IDEA, "--budget", BUDGET, "--dir", str(tmp_path)],
        ask=lambda prompt: "a",
        say=lambda text: None,
    )
    # Model output varies, so passing every check is not asserted; the accounting invariants are.
    assert code in (EXIT_OK, EXIT_INCOMPLETE)
    [run_dir] = (tmp_path / ".boss" / "runs").iterdir()
    events = read_events(run_dir / "ledger.jsonl")
    kinds = [e.event for e in events]
    assert kinds[:2] == [EventType.BOSS_CALL, EventType.APPROVED]
    # After the last round closes, the gate re-checks the delivered product (`scope: product`).
    closed_at = max(i for i, k in enumerate(kinds) if k is EventType.ROUND_CLOSED)
    assert all(
        k is EventType.CHECK_RESULT and events[i].data.get("scope") == "product"
        for i, k in enumerate(kinds)
        if i > closed_at
    )
    assert (run_dir / "report.md").read_text() == render_report(build_report(events))
    spent = total(events)
    assert spent.unknown_cost_events == 0
    assert 0 < spent.cost_micros < SPEND_CEILING_MICROS
    closed = events[closed_at].data
    assert closed["total"] == len(list((run_dir / "checks").glob("test_*.py")))
    assert (code == EXIT_OK) == closed["unlocked"]
