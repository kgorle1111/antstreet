"""`boss mcp`: the stdio MCP server is read-only, validates what a client sends, and answers in
JSON-RPC 2.0, one message per line."""

import io
import json
import subprocess
import sys

import pytest

from boss import mcp
from boss.ledger import EventType
from boss.rundir import Recorder, RunPaths

NO_CLAUDE = {"PATH": "/nonexistent", "BOSS_CLAUDE_BIN": "/nonexistent/claude"}


@pytest.fixture
def project(tmp_path):
    """A project with two runs; r2 is the latest and holds a signed investor approval."""
    project = tmp_path / "project"
    for run in ("r1", "r2"):
        paths = RunPaths(project / ".boss" / "runs" / run)
        with paths.writer() as ledger:
            record = Recorder(ledger, run, round=1)
            record("investor", EventType.APPROVED)
            record("gate", EventType.CHECK_RESULT, data={"check": "c01", "status": "passed"})
    return project


def talk(project, *messages, environ=NO_CLAUDE):
    """Send messages through `serve` as stdin lines; returns the parsed reply lines."""
    lines = [m if isinstance(m, str) else json.dumps(m) for m in messages]
    out = io.StringIO()
    assert mcp.serve(project, io.StringIO("\n".join(lines) + "\n"), out, environ) == 0
    return [json.loads(line) for line in out.getvalue().splitlines()]


def call(project, name, arguments=None, environ=NO_CLAUDE):
    params = {"name": name, "arguments": arguments or {}}
    [reply] = talk(project, {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": params},
                   environ=environ)  # fmt: skip
    result = reply["result"]
    return result["content"][0]["text"], result["isError"]


def test_initialize_answers_the_clients_legacy_version_and_offers_tools(project):
    init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}
    replies = talk(
        project,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
    )
    assert [r["id"] for r in replies] == [1, 2]  # the notification gets no reply
    result = replies[0]["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "antstreet"
    assert replies[1]["result"] == {}


def test_initialize_with_an_unknown_version_answers_the_latest_legacy_one(project):
    params = {"protocolVersion": "1999-01-01", "capabilities": {}, "clientInfo": {"name": "t"}}
    [reply] = talk(project, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params})
    assert reply["result"]["protocolVersion"] == mcp.LEGACY[0]


def test_a_modern_client_discovers_versions_and_a_wrong_one_is_refused(project):
    meta = {"_meta": {mcp.VERSION_KEY: "2026-07-28"}}
    found, listed, refused = talk(
        project,
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": meta},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": meta},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list",
         "params": {"_meta": {mcp.VERSION_KEY: "1900-01-01"}}},
    )  # fmt: skip
    assert "2026-07-28" in found["result"]["supportedVersions"]
    assert listed["result"]["resultType"] == "complete"
    assert refused["error"]["code"] == -32022
    assert refused["error"]["data"]["requested"] == "1900-01-01"


def test_tools_list_is_read_only_and_names_nothing_that_spends_or_approves(project):
    [reply] = talk(project, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = reply["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "list_runs",
        "status",
        "report",
        "verify_ledger",
        "doctor",
    ]
    for tool in tools:
        text = f"{tool['name']} {json.dumps(tool['inputSchema'])}".lower()
        for word in ("fund", "resume", "topup", "top_up", "approve", "live", "path", "dir"):
            assert word not in text, (tool["name"], word)
        assert tool["inputSchema"]["additionalProperties"] is False
    assert set(mcp._HANDLERS) == {t["name"] for t in tools}


def test_list_runs_newest_first(project):
    assert call(project, "list_runs") == ("r2\nr1", False)


def test_list_runs_in_a_project_without_runs_says_how_to_start(tmp_path):
    text, failed = call(tmp_path, "list_runs")
    assert not failed and "antstreet fund" in text


def test_status_reads_the_latest_run_or_the_one_named(project):
    text, failed = call(project, "status")
    assert not failed and text.startswith("r2: last event gate check_result")
    text, failed = call(project, "status", {"run": "r1"})
    assert not failed and text.startswith("r1: ")


def test_report_prints_the_board_report(project):
    text, failed = call(project, "report", {"run": "r1"})
    assert not failed and "BOARD REPORT" in text


def test_verify_ledger_passes_an_intact_run_and_fails_an_edited_one(project):
    text, failed = call(project, "verify_ledger", {"run": "r2"})
    assert not failed and "the ledger verifies: 2 lines" in text and "investor.key" in text
    ledger = project / ".boss" / "runs" / "r2" / "ledger.jsonl"
    first, rest = ledger.read_text().split("\n", 1)
    edited = json.loads(first)
    edited["round"] = 2  # the investor's approval moved to another round
    ledger.write_text(json.dumps(edited) + "\n" + rest)
    text, failed = call(project, "verify_ledger", {"run": "r2"})
    assert failed and "does NOT verify" in text
    text, failed = call(project, "status", {"run": "r2"})
    assert failed


def test_doctor_runs_without_live_and_reports_the_missing_cli(project):
    text, failed = call(project, "doctor")
    assert failed and "FAIL  claude cli" in text and "live call" not in text


@pytest.mark.parametrize(
    "bad", ["../r1", "r1/../r2", "/etc", ".", "..", "-h", "--live", "", "a b", 7]
)
@pytest.mark.parametrize("tool", ["status", "report", "verify_ledger"])
def test_a_run_id_that_is_not_one_safe_word_is_refused_with_a_way_forward(project, tool, bad):
    text, failed = call(project, tool, {"run": bad})
    assert failed and "refused" in text and "list_runs" in text


def test_an_unknown_run_says_which_runs_exist(project):
    text, failed = call(project, "status", {"run": "nope"})
    assert failed and "No run 'nope'" in text


def test_extra_arguments_are_refused(project):
    text, failed = call(project, "doctor", {"live": True})
    assert failed and "unknown arguments ['live']" in text


def test_long_output_is_cut_and_says_so(project, monkeypatch):
    monkeypatch.setitem(mcp._HANDLERS, "list_runs", lambda a, p, e: ("x" * 70_000, False))
    text, _ = call(project, "list_runs")
    assert len(text) < mcp.MAX_TEXT + 200 and "[cut 10000 characters" in text


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/fund"}, -32601),
        ({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, -32601),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "fund"}}, -32602),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "topup"}}, -32602),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": []}, -32602),
        ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600),
        ({"jsonrpc": "2.0", "id": None, "method": "ping"}, -32600),
        ([{"jsonrpc": "2.0", "id": 1, "method": "ping"}], -32600),
        ("{not json", -32700),
    ],
)
def test_bad_requests_get_json_rpc_errors(project, message, code):
    [reply] = talk(project, message)
    assert reply["error"]["code"] == code and "result" not in reply


def test_an_oversized_line_is_refused_and_the_next_one_still_answered(project, monkeypatch):
    monkeypatch.setattr(mcp, "MAX_LINE", 64)
    ping = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    big, ok = talk(project, json.dumps({"pad": "x" * 500}), ping)
    assert big["error"]["code"] == -32600 and ok == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_antstreet_mcp_speaks_on_stdout_only_in_protocol_lines(project):
    """The real entry point, end to end: everything on stdout parses as JSON-RPC."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "t"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "status", "arguments": {}}},
    ]  # fmt: skip
    done = subprocess.run(
        [sys.executable, "-m", "boss.cli", "mcp", "--dir", str(project)],
        input="".join(json.dumps(r) + "\n" for r in requests),
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[1]["result"]["content"][0]["text"].startswith("r2: ")
