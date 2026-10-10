"""docs/ARCHITECTURE.md stays true: its module map, event names, limits and 'not built' list."""

import ast
import importlib
import inspect
import re

import pytest
from docs_support import DOCS, ROOT, code_spans, money, read, section, table

from boss import (
    audit,
    boss,
    budget,
    cli,
    context,
    firm,
    gate,
    limits,
    pipeline,
    retry,
    rule,
    runner,
    worker,
)
from boss.bench import run as bench_run
from boss.ledger import Event, EventType

DOC = DOCS / "ARCHITECTURE.md"
SRC = ROOT / "src" / "boss"


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def module_files() -> set[str]:
    return {p.relative_to(SRC).as_posix() for p in SRC.rglob("*.py")}


def test_every_module_is_in_the_module_map_and_every_mapped_module_exists(text):
    rows = table(section(text, "Module map"))
    mapped = [row[0].strip("`") for row in rows]
    assert len(mapped) == len(set(mapped)), "a module is listed twice"
    real = module_files()
    assert set(mapped) - real == set(), (
        f"named in the map but not in src/boss: {set(mapped) - real}"
    )
    assert real - set(mapped) == set(), (
        f"in src/boss but missing from the map: {real - set(mapped)}"
    )


def test_every_module_row_says_what_it_owns_and_what_it_never_does(text):
    for row in table(section(text, "Module map")):
        assert len(row) == 3 and row[1] and row[2], f"row needs three filled cells: {row[0]}"


def test_every_prompt_file_and_prompt_constant_is_named(text):
    prompts = {p.name for p in (SRC / "prompts").glob("*.md")}
    used = {
        boss.TERM_SHEET_PROMPT,
        boss.MULTI_TASK_PROMPT,
        firm.BUILDER_PROMPT,
        bench_run.SOLO_PROMPT,
        audit.AUDIT_PROMPT,
    }
    assert used <= prompts, "code names a prompt file that does not exist"
    for name in prompts:
        assert name in text, f"prompt {name} is not named in ARCHITECTURE.md"


def test_actors_in_the_roles_table_are_accepted_by_the_ledger(text):
    actors = [row[2].strip("`") for row in table(section(text, "Roles")) if row[2] != "none"]
    assert len(actors) == 5
    for actor in actors:
        name = actor.replace("<name>", "w1")
        Event(run="r", round=0, actor=name, event=EventType.STOPPED)  # raises on an unknown actor


def _events_used_by(path) -> set[str]:
    tree = ast.parse(read(path))
    return {
        str(EventType[node.attr].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "EventType"
    }


def test_the_control_flow_table_names_only_real_events_and_every_loop_event(text):
    body = "\n".join("|".join(row) for row in table(section(text, "Control flow of `firm.py`")))
    named = {s for s in code_spans(body) if re.fullmatch(r"[a-z_]+", s)}
    valid = {e.value for e in EventType}
    events_named = named & valid
    used = _events_used_by(SRC / "firm.py")
    assert used <= events_named, f"firm.py writes {used - events_named} but the table omits it"
    # words such as `fired` are events; anything else in code spans must not look like one
    unknown = {s for s in named - valid if s.endswith(("_end", "_start", "_result", "_closed"))}
    assert not unknown, f"table names events that do not exist: {unknown}"


def _resolve(dotted: str) -> object:
    module, *path = dotted.split(".")
    obj: object = importlib.import_module(f"boss.{module}")
    for part in path:
        obj = getattr(obj, part)
    return obj


def test_fixed_limits_match_the_code_and_the_named_symbols_exist(text):
    policy, run_limits = rule.FiringPolicy(), limits.RunLimits()
    expected = {
        "Workers per task": str(firm.MAX_WORKERS_PER_TASK),
        "Context bundle, characters": str(context.MAX_BUNDLE_CHARS),
        "Default worker slice": money(firm.DEFAULT_SLICE_MICROS),
        "Reserve held back from every cap": money(budget.RESERVE_MICROS),
        "Smallest slice cap": money(budget.MIN_SLICE_MICROS),
        "Slices in a whole run": str(run_limits.max_slices),
        "Workers in a whole run": str(run_limits.max_workers),
        "Stall slices before firing": str(policy.stall_slices),
        "Counted slices before firing": str(policy.max_slices),
        "Infrastructure attempts": str(retry.infra_action.__kwdefaults__["max_attempts"]),
        "One worker slice, wall clock": f"{int(runner.DEFAULT_TIMEOUT_S)} s",
        "One check, wall clock": f"{int(gate.DEFAULT_TIMEOUT_S)} s",
        "One boss call, wall clock": f"{int(boss.DEFAULT_TIMEOUT_S)} s",
        "One boss call, cap": money(boss.DEFAULT_CAP_MICROS),
        "Checks in a draft": f"1 to {boss.MAX_CHECKS}",
        "Oldest supported `claude` CLI": ".".join(map(str, worker.MIN_CLI_VERSION)),
    }
    rows = {row[0]: row for row in table(section(text, "Fixed limits"))}
    for name, value in expected.items():
        assert name in rows, f"no row named {name!r}"
        assert rows[name][1].strip("`") == value, f"{name}: doc says {rows[name][1]}, code {value}"
    for name, row in rows.items():
        symbol = row[2].strip("`")
        if "." in symbol:
            _resolve(symbol)  # raises if the named symbol is gone
        assert name in expected or name == "One check on an empty workspace", f"unchecked: {name}"


def test_the_empty_workspace_timeout_is_thirty_seconds(text):
    source = read(SRC / "termsheet.py")
    assert "timeout_s=30.0" in source
    assert "| One check on an empty workspace | 30 s |" in text


def _uses(name: str) -> list[str]:
    """Files under src/boss that mention EventType.<name>, not counting the enum itself."""
    return sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if p.name != "ledger.py" and f"EventType.{name}" in read(p)
    )


def _callers(name: str, *, skip: tuple[str, ...]) -> list[str]:
    return sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if p.name not in skip and name in read(p)
    )


def test_not_built_claims_are_still_true(text):
    body = section(text, "Not built")
    # nothing writes denied; `topped_up` is read by the budget (and counted by the KPIs as a step
    # the investor took) and written by `boss topup`, and by the pipeline after the investor's
    # yes to a fix round under `--fix-after-stop`
    assert _uses("DENIED") == [] and "`denied`" in body
    uses = ["budget.py", "cli.py", "kpi.py", "pipeline.py"]
    assert _uses("TOPPED_UP") == uses and "topped_up" not in body
    # the amendment is no longer a gap: it is written (see the test below), so it is not listed
    assert "added_checks" not in body and "amendment" not in body
    # a set-aside task is never re-opened: state keeps it abandoned and the loop skips it
    assert "not state.tasks[task.id].abandoned" in read(SRC / "firm.py")
    assert "already set aside" in body


def test_an_amendment_is_written_by_the_pipeline_only_after_the_investor_says_yes(text):
    # Writers of `added_checks`: the pipeline, in `_amend`; readers: the loop (`firm.py`).
    skip = ("state.py", "briefs.py", "critic.py")
    assert _callers("added_checks", skip=skip) == ["firm.py", "pipeline.py"]
    assert 'e.data.get("added_checks"' in read(SRC / "firm.py")
    amend = inspect.getsource(pipeline.Pipeline._amend)
    assert '"added_checks": [c.id for c in checks]' in amend
    assert 'Recorder(self.ledger, self.run_id, n)("investor", EventType.APPROVED' in amend
    assert "if answer not in YES:" in amend
    assert amend.index("if answer not in YES:") < amend.index("EventType.APPROVED")
    # the approval is recorded before the sheet on disk changes, so a crash between them leaves
    # the old, still approved sheet, never one nobody approved
    assert amend.index("EventType.APPROVED") < amend.index("TERM_SHEET_FILE")
    body = section(text, "The roles around the loop")
    assert "`added_checks`" in body and "investor `approved` event" in body


def test_the_roles_section_names_real_methods_and_the_one_module_that_calls_roles(text):
    body = section(text, "The roles around the loop")
    methods = {s.split(".")[1] for s in code_spans(body) if re.fullmatch(r"Pipeline\.\w+", s)}
    assert {"plan", "advisor", "after_build", "_book"} <= methods
    for name in methods:
        assert callable(getattr(pipeline.Pipeline, name)), f"Pipeline.{name} does not exist"
    for name in ("draft_staged", "review_term_sheet", "run_firm", "draft_boss"):
        assert f"`{name}`" in body
    row = next(r for r in table(section(text, "Module map")) if r[0] == "`pipeline.py`")
    assert "record_start" not in row[1] and "call a role that was not chosen" in row[2]
    assert "`pipeline.py` is the" in section(text, "Roles")


def test_what_the_document_no_longer_calls_missing_is_built_and_named(text):
    body = section(text, "Not built")
    firm_source = read(SRC / "firm.py")
    # the loop calls retry.plan_pressure, through _Firm._plan_pressure, unless the pause is off
    assert _callers("plan_pressure", skip=("retry.py",)) == ["firm.py"]
    assert "retry.plan_pressure(run.rate_limit" in firm_source
    assert firm.FirmConfig().plan_pause_at == 0.95 and "plan_pressure" not in body
    # `boss resume` exists, and it calls repair_torn_tail
    commands = cli._parser()._subparsers._group_actions[0].choices
    assert "resume" in commands and "boss resume" not in body
    assert "repair_torn_tail" in inspect.getsource(cli._resume_run)
    assert "repair_torn_tail" not in body
    assert _callers("repair_torn_tail", skip=("ledger.py",)) == ["cli.py"]
    # tasks run in parallel: a wave of up to `parallel` slices in a thread pool
    assert firm.FirmConfig().parallel == 1 and "ThreadPoolExecutor" in firm_source
    assert "--parallel" in commands["fund"].format_help() and "in parallel" not in body
