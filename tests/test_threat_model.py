"""docs/THREAT_MODEL.md stays honest: every test it cites exists, and its table is well formed."""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "THREAT_MODEL.md"
STATUSES = {"controlled", "partly controlled", "accepted"}
REF = re.compile(r"tests/([A-Za-z0-9_]+\.py)::([A-Za-z0-9_]+)")
ROW = re.compile(r"^\|\s*(T\d+)\s*\|")
STATUS = re.compile(r"^`([a-z ]+)`")


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rows(text: str) -> list[dict[str, str]]:
    found = []
    for line in text.splitlines():
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 5, f"a threat row needs 5 cells, got {len(cells)}: {line[:60]}"
        found.append(dict(zip(("id", "threat", "control", "tests", "status"), cells, strict=True)))
    return found


def status_of(row: dict[str, str]) -> str:
    match = STATUS.match(row["status"])
    return match.group(1) if match else ""


def defined_tests(path: Path) -> set[str]:
    """Names of functions defined at module level or directly in a class; parsed, never imported."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names |= {
                n.name for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            }
    return names


def test_the_document_lists_threats(rows):
    assert len(rows) >= 20


def test_threat_ids_are_unique_and_consecutive(rows):
    ids = [r["id"] for r in rows]
    assert ids == [f"T{n:02d}" for n in range(1, len(ids) + 1)]


def test_every_row_has_a_threat_a_control_and_an_allowed_status(rows):
    problems = []
    for r in rows:
        if not r["threat"]:
            problems.append(f"{r['id']}: empty threat")
        if not r["control"]:
            problems.append(f"{r['id']}: empty control")
        if status_of(r) not in STATUSES:
            problems.append(f"{r['id']}: status must start with one of {sorted(STATUSES)}")
    assert not problems, "\n".join(problems)


def test_every_cited_test_exists(text):
    cited = REF.findall(text)
    assert cited, "the document cites no tests"
    problems = []
    for filename, name in sorted(set(cited)):
        path = ROOT / "tests" / filename
        if not path.is_file():
            problems.append(f"tests/{filename} does not exist (cited as {name})")
        elif name not in defined_tests(path):
            problems.append(f"tests/{filename} does not define {name}")
        elif not name.startswith("test_"):
            problems.append(f"tests/{filename}::{name} would not be collected by pytest")
    assert not problems, "\n".join(problems)


def test_controlled_and_partly_controlled_rows_cite_a_test(rows):
    bare = [r["id"] for r in rows if status_of(r) != "accepted" and not REF.search(r["tests"])]
    assert not bare, f"rows with a control but no cited test: {bare}"


def test_partly_controlled_and_accepted_rows_say_what_remains(rows):
    thin = [
        r["id"]
        for r in rows
        if status_of(r) in ("partly controlled", "accepted")
        and len(r["status"].split(":", 1)[-1].strip()) < 20
    ]
    assert not thin, f"rows that do not say what remains or why: {thin}"


def test_the_late_hook_control_is_claimed_only_with_its_tests(rows):
    row = next(r for r in rows if r["id"] == "T21")
    assert "tests/test_runner_isolation_late.py::" in row["tests"]
    assert "checked once" not in row["status"]
    source = (ROOT / "src" / "antstreet" / "runner.py").read_text(encoding="utf-8")
    assert "reader.hook_events" in source and "require_isolation(reader.init" in source


def test_the_ledger_row_says_resume_repairs_a_torn_tail_and_the_code_does(rows):
    row = next(r for r in rows if r["id"] == "T28")
    assert "repair_torn_tail" in row["control"] and "`antstreet resume` calls it" in row["control"]
    assert "no command calls" not in row["status"] and "Not wired in" not in row["status"]
    assert (
        "tests/test_cli.py::test_resume_repairs_a_ledger_whose_last_line_was_cut_off_and_says_so"
        in (row["tests"])
    )
    callers = [
        p.name
        for p in (ROOT / "src" / "antstreet").rglob("*.py")
        if p.name != "ledger.py" and "repair_torn_tail" in p.read_text(encoding="utf-8")
    ]
    assert callers == ["cli.py"], (
        "the only caller is `antstreet resume`: update T28 if that changes"
    )
    # The repair comes before the first read of the ledger, in `_resume_run` (`_resume` finds
    # the run and turns a held lock into a message).
    tree = ast.parse((ROOT / "src" / "antstreet" / "cli.py").read_text(encoding="utf-8"))
    resume = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_resume_run"
    )
    lines = {
        name: min(
            c.lineno
            for c in ast.walk(resume)
            if isinstance(c, ast.Call)
            and name in (getattr(c.func, "id", None), getattr(c.func, "attr", None))
        )
        for name in ("repair_torn_tail", "events")  # `paths.events()` reads the ledger
    }
    assert lines["repair_torn_tail"] < lines["events"]
