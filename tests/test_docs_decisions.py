"""docs/DECISIONS.md stays true: well-formed entries, real references, real evidence."""

import ast
import json
import re
from pathlib import Path

import pytest
from docs_support import DOCS, ROOT, code_spans, read

DOC = DOCS / "DECISIONS.md"
FIELDS = ("Status", "Decision", "Why", "Rejected", "Evidence")
STATUS = re.compile(r"^`(in force|under evaluation|superseded by (D\d{2}))`\.?$")
HEADING = re.compile(r"^### (D\d+): (.+)$", re.M)
PATH = re.compile(r"^(?:\.\./)?((?:src|tests|docs|bench)/[\w./-]+?)(?:::(\w+))?$")
FIELD_LINE = re.compile(rf"^- ({'|'.join(FIELDS)}): ?", re.M)
# a topic that must have an entry, found by a phrase in its title
REQUIRED_TOPICS = (
    "no shell",
    "path-scoped",
    "--safe-mode",
    "micro-dollars",
    "unknown cost is none",
    "ledger is the only state",
    "firing rule",
    "one reassignment",
    "reserve",
    "word for word",
    "disputed check",
    "--effort",
    "unknown cost is charged",
    "re-verified",
    "hard run limits",
    "refused tool call",
    "same idea, model, tools and budget",
    "hidden checks",
    "descriptive only",
    "ledger events",
    "lifts a stop",
    "new session id",
    "charged at its cap",
    "credible",
    "sandbox that denies by default",
    "precision on the reference",
)


def parse(text: str) -> list[dict[str, str]]:
    """Entries in document order: id, title and each field's text."""
    entries = []
    heads = list(HEADING.finditer(text))
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[head.end() : end]
        entry = {"id": head.group(1), "title": head.group(2)}
        marks = list(FIELD_LINE.finditer(body))
        for j, mark in enumerate(marks):
            stop = marks[j + 1].start() if j + 1 < len(marks) else len(body)
            entry[mark.group(1)] = " ".join(body[mark.end() : stop].split())
        entries.append(entry)
    return entries


def defined_tests(path: Path) -> set[str]:
    """Names of functions defined at module level or directly in a class; parsed, never imported."""
    tree = ast.parse(read(path), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names |= {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    return names


def problems_in(text: str, base: Path = DOCS) -> list[str]:
    """Every way the log breaks its own rules; empty when it is sound."""
    entries = parse(text)
    found = []
    ids = [e["id"] for e in entries]
    if ids != [f"D{n:02d}" for n in range(1, len(ids) + 1)]:
        found.append(f"ids are not unique and consecutive from D01: {ids}")
    for e in entries:
        for name in FIELDS[1:]:
            if len(e.get(name, "")) < 12:
                found.append(f"{e['id']}: field {name} is missing or empty")
        status = STATUS.match(e.get("Status", ""))
        if not status:
            found.append(
                f"{e['id']}: status must be in force, under evaluation or superseded by Dxx"
            )
        elif status.group(2) and (status.group(2) not in ids or status.group(2) == e["id"]):
            found.append(f"{e['id']}: superseded by {status.group(2)}, which is not another entry")
        for span in code_spans(" ".join(e.values())):
            match = PATH.match(span.split(" ")[0])
            if not match:
                continue
            path = ROOT / match.group(1)
            if not path.exists():
                found.append(f"{e['id']}: cites {match.group(1)}, which does not exist")
            elif match.group(2) and not (
                match.group(2).startswith("test_") and match.group(2) in defined_tests(path)
            ):
                found.append(f"{e['id']}: {match.group(1)} has no test {match.group(2)}")
    for link in re.findall(r"\]\(([^)#]+)", text):
        if not link.startswith("http") and not (base / link).exists():
            found.append(f"link {link} points at nothing")
    return found


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def test_the_log_is_well_formed(text):
    assert problems_in(text) == []


def test_every_required_topic_has_an_entry(text):
    titles = " | ".join(e["title"].lower() for e in parse(text))
    missing = [t for t in REQUIRED_TOPICS if t not in titles]
    assert not missing, f"no entry titled for: {missing}"


def test_the_checker_catches_each_way_an_entry_can_be_wrong():
    good = (
        "### D01: one\n\n- Status: `in force`\n- Decision: something decided here.\n"
        "- Why: a reason that is long.\n- Rejected: another way that lost.\n"
        "- Evidence: `tests/test_ledger.py::test_corrupt_line_raises_with_its_line_number`\n"
    )
    assert problems_in(good) == []
    cases = {
        "duplicate id": good + good,
        "gap in ids": good.replace("D01", "D02"),
        "missing field": good.replace("- Why: a reason that is long.\n", ""),
        "bad status": good.replace("`in force`", "`maybe`"),
        "supersedes nothing": good.replace("`in force`", "`superseded by D09`"),
        "supersedes itself": good.replace("`in force`", "`superseded by D01`"),
        "missing file": good.replace("tests/test_ledger.py", "tests/test_nowhere.py"),
        "missing test": good.replace("test_corrupt_line", "test_no_such_line"),
        "dead link": good + "[x](nowhere.md)\n",
    }
    for name, bad in cases.items():
        assert problems_in(bad), f"the checker accepted: {name}"


def _result(name: str) -> dict:
    text = read(ROOT / "tests" / "fixtures" / name)
    if name.endswith(".json"):
        return json.loads(text)
    parsed = [json.loads(line) for line in text.splitlines() if line.strip()]
    return next(e for e in parsed if e.get("type") == "result")


def test_probe_figures_quoted_in_the_log_match_the_recorded_fixtures(text):
    entries = {e["id"]: " ".join(e.values()) for e in parse(text)}
    capped = _result("stream_budget_capped_2.1.285.jsonl")
    assert "($0.006)" in capped["errors"][0]
    assert f"{capped['total_cost_usd']:.4f}" == "0.0079" and "$0.0079" in entries["D18"]
    auth = _result("stream_auth_expired_2.1.285.jsonl")
    assert (auth["total_cost_usd"], auth["api_error_status"], auth["subtype"]) == (
        0,
        401,
        "success",
    )
    assert "401" in entries["D11"] and "true 0" in entries["D05"]
    boss_call = _result("json_boss_schema_call_2.1.285.json")
    assert f"{boss_call['total_cost_usd']:.4f}" == "0.0036" and "$0.0036" in entries["D04"]
    safe = _result("stream_safe_mode_ok_2.1.285.jsonl")
    assert f"{safe['total_cost_usd']:.3f}" == "0.010" and "$0.010" in entries["D07"]


def test_the_defaults_quoted_in_the_log_are_the_defaults_in_the_code(text):
    from boss import budget, limits, rule

    entries = {e["id"]: " ".join(e.values()) for e in parse(text)}
    policy, run_limits = rule.FiringPolicy(), limits.RunLimits()
    assert f"default {policy.stall_slices} counted slices" in entries["D15"]
    assert f"(default {policy.max_slices})" in entries["D15"]
    assert f"slices started ({run_limits.max_slices})" in entries["D22"]
    assert f"workers hired ({run_limits.max_workers}," in entries["D22"]
    assert f"reserve (default ${budget.RESERVE_MICROS / 1e6:.2f}" in entries["D18"]
    assert f"cap of ${budget.MIN_SLICE_MICROS / 1e6:.3f}" in entries["D18"]


def test_the_draft_baseline_quoted_in_the_log_is_the_one_in_the_method_document(text):
    entry = {e["id"]: " ".join(e.values()) for e in parse(text)}["D36"]
    method = " ".join(read(ROOT / "bench" / "METHOD.md").split())
    assert "10 of 134 checks wrong, 38 of 65 mutants killed" in method
    assert "4 of 134 wrong, 39 of 65 killed" in method
    assert [round(100 * (134 - w) / 134) for w in (10, 4)] == [93, 97]
    assert [round(100 * k / 65) for k in (38, 39)] == [58, 60]
    assert "precision 93% and 97%" in entry and "recall 58% and 60%" in entry
    assert "(10 and 4 of 134 wrong)" in entry and "(38 and 39 of 65)" in entry
