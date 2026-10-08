"""B71: a cell cut off by the environment is excluded from every count, whatever its product scored.

Old result files already on disk carry `failure_class: null` for a passing cut-off cell, so the
rule is derived from `outcome`, not only from the stored class.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from antstreet.bench.kpi import kpi_card
from antstreet.bench.paired import compare
from antstreet.bench.results import INFRA_OUTCOMES, CellResult
from antstreet.bench.table import per_task, summarize

PASS = {"a": "passed", "b": "passed"}


def cell(**over: object) -> CellResult:
    fields: dict[str, object] = {
        "task": "t1",
        "arm": "single",
        "rep": 1,
        "set_hash": "h",
        "model": "m",
        "budget_micros": 1,
        "hidden": PASS,
        "visible_passed": None,
        "visible_total": None,
        "cost_micros": 1,
        "boss_micros": 0,
        "unknown_cost_events": 0,
        "outcome": "completed",
        "failure_class": None,
        "duration_s": 1.0,
    }
    fields.update(over)
    return CellResult(**fields)  # type: ignore[arg-type]


def old_format_usage_limit(tmp_path: Path, **over: object) -> CellResult:
    """A passing `usage_limit` result as written before B71: loaded from disk, class null."""
    raw = asdict(cell(outcome="usage_limit", **over))
    assert raw["failure_class"] is None
    path = tmp_path / "result.json"
    path.write_text(json.dumps(raw))
    return CellResult.load(path)


def test_the_predicate_reads_the_outcome_not_only_the_stored_class(tmp_path):
    old = old_format_usage_limit(tmp_path)
    assert old.passed and old.failure_class is None and not old.counted
    assert not cell(outcome="boss:login").counted  # prefix stripped
    assert not cell(outcome="isolation").counted
    assert not cell(failure_class="infrastructure").counted  # stored class alone is enough
    assert cell(outcome="completed").counted  # a passing ordinary cell still counts
    assert cell(outcome="boss:completed", hidden={"a": "failed"}, failure_class="model").counted


@pytest.mark.parametrize("outcome", sorted(INFRA_OUTCOMES))
def test_every_infrastructure_outcome_excludes_a_passing_cell(outcome):
    assert not cell(outcome=outcome).counted
    assert not cell(outcome=f"boss:{outcome}").counted


def test_table_excludes_an_old_passing_usage_limit_cell(tmp_path):
    cells = [
        old_format_usage_limit(tmp_path),
        cell(rep=2),
        cell(rep=3, hidden={"a": "failed"}, failure_class="model"),
    ]
    (s,) = summarize(cells)
    assert (s.cells, s.infrastructure, s.passed) == (2, 1, 1)
    assert per_task(cells) == [("t1", {"single": (1, 2)})]


def test_table_excludes_a_boss_login_cell_that_passed():
    (s,) = summarize([cell(outcome="boss:login", arm="firm"), cell(arm="firm", rep=2)])
    assert (s.cells, s.infrastructure, s.passed) == (1, 1, 1)


def test_kpi_excludes_an_old_passing_usage_limit_cell(tmp_path):
    cells = [old_format_usage_limit(tmp_path, arm="firm"), cell(arm="firm", rep=2)]
    card = kpi_card(cells)
    assert (card.counted, card.delivered, card.infrastructure) == (1, 1, 1)


def test_paired_excludes_an_old_passing_usage_limit_cell(tmp_path):
    a = [old_format_usage_limit(tmp_path, arm="firm", task="t0"), cell(arm="firm", task="t1")]
    b = [cell(arm="single", task="t0"), cell(arm="single", task="t1")]
    p = compare(a, b, "firm", "single", "delivery", resamples=2000)
    assert (p.tasks, p.unpaired, p.infrastructure) == (1, 1, 1)
